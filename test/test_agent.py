import json
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import inject
import pytest
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    ToolMessage,
)
from langgraph.graph import END

import internal.core.agent.function_call_agent as agent_module
from internal.core.agent import (
    DEFAULT_AGENT_TOOLS,
    AgentConfig,
    AgentEventEntity,
    AgentQueueManager,
    FunctionCallAgent,
)
from internal.core.message_processor import MessageProcessor
from internal.core.tools.builtin_tools import BuiltinProviderManager
from internal.entity import EventType, InvokeFrom, PublishFrom
from internal.model.conversation import Conversation, Message, MessageAgentThought
from internal.pkg.response import HttpCode
from internal.service.agent_service import (
    MESSAGE_STATUS_COMPLETED,
    MESSAGE_STATUS_ERROR,
)
from pkg.sqlalchemy import db

# 会话名前缀，接口用例用它来识别并清理自己造的数据
DEBUG_CONVERSATION_PREFIX = "Agent调试用例"
# TODO: 等待授权认证模块完成后再进行切换调整
TEST_ACCOUNT_ID = "a666a888-8888-6666-1234-b9d69212aaaa"


def _collect(manager: AgentQueueManager, task_id: str) -> list[AgentEventEntity]:
    """把队列里已有的事件读完，遇到停止标记结束。"""
    return list(
        manager.listen(task_id, timeout=2, heartbeat_interval=1, poll_interval=0.05)
    )


def _fake_tool():
    """构造一个假的 google_serper 工具，避免真实联网。"""
    tool = MagicMock()
    tool.name = "google_serper"
    tool.invoke.return_value = "杭州今天晴，25 度"
    return tool


def _fake_provider(tool=None):
    """假的工具提供商：按名返回假工具实例与展示名。"""
    provider = MagicMock()
    provider.get_tool_instance.return_value = tool
    provider.get_tool_entity.return_value = SimpleNamespace(
        name="google_serper" if tool is not None else "", label="谷歌搜索"
    )
    return provider


def _fake_provider_manager(tool=None):
    """假的内置插件管理器：只有一个服务商。"""
    manager = MagicMock()
    manager.get_providers.return_value = [_fake_provider(tool)]
    return manager


def _builtin_like_manager(names: list[str]):
    """模拟真实插件管理器：按工具名给出实体与实例，用于验证默认工具。"""
    provider = MagicMock()
    provider.get_tool_entities.return_value = [
        SimpleNamespace(name=name, label=name, params=[]) for name in names
    ]

    def instance(name, **values):
        tool = MagicMock()
        tool.name = name
        return tool

    provider.get_tool_instance.side_effect = instance
    manager = MagicMock()
    manager.get_providers.return_value = [provider]
    return manager


def _fake_model(responses: list[list[AIMessageChunk]]):
    """假的流式模型：每次 stream 调用返回一组预设的分片。"""
    model = MagicMock()
    model.bind_tools.return_value = model
    model.stream.side_effect = [iter(chunks) for chunks in responses]
    return model


class TestAgentQueueManager:
    """队列管理器：发布、监听、心跳、超时、停止与任务状态。"""

    def test_publish_then_listen_until_stop(self):
        manager = AgentQueueManager()
        manager.publish("task-a", AgentEventEntity(event=EventType.AGENT_MESSAGE))
        manager.publish("task-a", AgentEventEntity(event=EventType.AGENT_END))
        manager.stop_listen("task-a")

        events = _collect(manager, "task-a")
        assert [event.event for event in events] == [
            EventType.AGENT_MESSAGE,
            EventType.AGENT_END,
        ]
        # 事件被补齐 task_id，前端不用自己猜
        assert all(event.task_id == "task-a" for event in events)

    def test_listen_emits_ping_when_queue_idle(self):
        manager = AgentQueueManager()

        def produce():
            time.sleep(0.2)
            manager.publish("task-b", AgentEventEntity(event=EventType.AGENT_END))
            manager.stop_listen("task-b")

        threading.Thread(target=produce, daemon=True).start()
        events = list(
            manager.listen(
                "task-b", timeout=3, heartbeat_interval=0.05, poll_interval=0.02
            )
        )
        assert events[0].event == EventType.PING
        assert events[-1].event == EventType.AGENT_END

    def test_listen_emits_timeout_and_closes(self):
        manager = AgentQueueManager()
        events = list(
            manager.listen(
                "task-c", timeout=0.1, heartbeat_interval=1, poll_interval=0.02
            )
        )
        assert [event.event for event in events] == [EventType.TIMEOUT]

    def test_status_flags_are_recorded(self):
        manager = AgentQueueManager()
        assert manager.is_started("task-d") is False
        manager.publish("task-d", AgentEventEntity(event=EventType.AGENT_MESSAGE))
        assert manager.is_started("task-d") is True
        assert manager.is_stopped("task-d") is False
        # 以停止来源发布，等价于把任务标记为已停止
        manager.publish("task-d", AgentEventEntity(event=EventType.STOP), PublishFrom.STOP)
        assert manager.is_stopped("task-d") is True

    def test_stop_listen_clears_status(self):
        manager = AgentQueueManager()
        manager.publish("task-e", AgentEventEntity(event=EventType.AGENT_MESSAGE))
        manager.stop_listen("task-e")
        # 监听结束后队列与状态都该清干净，避免任务号复用出错
        assert len(_collect(manager, "task-e")) == 1
        assert manager.is_started("task-e") is False
        assert manager.is_stopped("task-e") is False


class TestAgentEventEntity:
    """事件实体：字段齐全，能被 JSON 序列化后直接发往前端。"""

    def test_to_dict_is_json_serializable(self):
        event = AgentEventEntity(
            task_id="task-f",
            event=EventType.AGENT_THOUGHT,
            tool="google_serper",
            tool_input={"query": "杭州天气"},
            message=[{"role": "user", "content": "杭州天气怎么样"}],
        )
        payload = json.loads(json.dumps(event.to_dict(), ensure_ascii=False))
        assert payload["task_id"] == "task-f"
        assert payload["event"] == EventType.AGENT_THOUGHT
        assert payload["tool_input"] == {"query": "杭州天气"}
        # 每个事件自带 id，落库时直接复用
        assert payload["id"] == event.id


class TestAgentConfig:
    """智能体配置：从请求字典还原，并合并系统提示词。"""

    def test_from_dict_and_merged_prompt(self):
        config = AgentConfig.from_dict(
            {
                "llm": "deepseek-v4-flash",
                "system_prompt": "你是一个助手",
                "preset_prompt": "回答要简短",
                "enable_long_term_memory": True,
                "tools": ["google_serper"],
            }
        )
        assert config.llm == "deepseek-v4-flash"
        assert config.enable_long_term_memory is True
        assert config.tools == ["google_serper"]
        assert config.merged_prompt() == "你是一个助手\n\n回答要简短"

    def test_defaults(self):
        config = AgentConfig()
        assert config.enable_long_term_memory is False
        assert config.tools == []
        assert config.merged_prompt() == ""


class TestFunctionCallAgentGraph:
    """FunctionCallAgent：节点产出与路由函数。"""

    def _agent(self, monkeypatch, responses, config=None, tool=None):
        queue_manager = AgentQueueManager()
        agent = FunctionCallAgent(
            provider_manager=_fake_provider_manager(tool),
            queue_manager=queue_manager,
            task_id="task-agent",
            config=config or AgentConfig(),
        )
        model = _fake_model(responses)
        monkeypatch.setattr(agent_module, "ChatOpenAI", lambda **kwargs: model)
        return agent, queue_manager, model

    def test_default_tools_come_from_builtin_manager(self):
        agent = FunctionCallAgent(
            provider_manager=_builtin_like_manager(
                ["google_serper", "gaode_weather", "google_test"]
            ),
            queue_manager=AgentQueueManager(),
            task_id="task-tools",
            config=AgentConfig(),
        )
        # 没点名工具时用默认的内置工具，点名后只取点名的
        assert [tool.name for tool in agent._resolve_tools()] == list(
            DEFAULT_AGENT_TOOLS
        )
        agent.config = AgentConfig(tools=["gaode_weather"])
        assert [tool.name for tool in agent._resolve_tools()] == ["gaode_weather"]

    def test_default_tools_are_bound_to_model(self, monkeypatch):
        queue_manager = AgentQueueManager()
        agent = FunctionCallAgent(
            provider_manager=_builtin_like_manager(["google_serper", "gaode_weather"]),
            queue_manager=queue_manager,
            task_id="task-bind",
            config=AgentConfig(),
        )
        model = _fake_model([[AIMessageChunk(content="好的")]])
        monkeypatch.setattr(agent_module, "ChatOpenAI", lambda **kwargs: model)

        agent._model()
        bound = model.bind_tools.call_args[0][0]
        assert [tool.name for tool in bound] == ["google_serper", "gaode_weather"]

    def test_route_function_decides_flow(self, monkeypatch):
        agent, _, _ = self._agent(monkeypatch, [[]])

        def state(messages):
            return {"messages": messages, "history": [], "long_term_memory": ""}

        assert agent._route(state([AIMessage(content="完成")])) == END
        assert (
            agent._route(
                state(
                    [
                        AIMessage(
                            content="",
                            tool_calls=[
                                {
                                    "name": "google_serper",
                                    "args": {},
                                    "id": "1",
                                    "type": "tool_call",
                                }
                            ],
                        )
                    ]
                )
            )
            == "tool"
        )
        assert (
            agent._route(state([ToolMessage(content="结果", tool_call_id="1")])) == "llm"
        )

    def test_run_publishes_message_and_end(self, monkeypatch):
        responses = [
            [
                AIMessageChunk(content="杭州"),
                AIMessageChunk(
                    content="今天晴",
                    usage_metadata={"input_tokens": 3, "output_tokens": 4, "total_tokens": 7},
                ),
            ]
        ]
        agent, queue_manager, _ = self._agent(monkeypatch, responses)
        answer = agent.run("杭州天气怎么样")
        events = _collect(queue_manager, "task-agent")

        assert answer == "杭州今天晴"
        # 分片逐条输出，前端边收边拼
        assert [event.event for event in events][:2] == [
            EventType.AGENT_MESSAGE,
            EventType.AGENT_MESSAGE,
        ]
        assert events[-1].event == EventType.AGENT_END
        assert events[-1].answer == "杭州今天晴"
        assert events[-1].total_token_count == 7
        assert events[-1].latency >= 0

    def test_run_uses_system_prompt_and_history(self, monkeypatch):
        agent, queue_manager, model = self._agent(
            monkeypatch, [[AIMessageChunk(content="好的")]], config=AgentConfig(system_prompt="只回答天气")
        )
        agent.run("杭州天气怎么样", history=[HumanMessage(content="上一轮问题")])
        sent = model.stream.call_args[0][0]
        assert sent[0].content == "只回答天气"
        assert [item.content for item in sent[1:]] == ["上一轮问题", "杭州天气怎么样"]

    def test_run_calls_tool_then_answers(self, monkeypatch):
        tool = _fake_tool()
        responses = [
            [
                AIMessageChunk(
                    content="",
                    tool_calls=[
                        {
                            "name": "google_serper",
                            "args": {"query": "杭州天气"},
                            "id": "call_1",
                            "type": "tool_call",
                        }
                    ],
                )
            ],
            [AIMessageChunk(content="根据搜索结果，杭州今天晴")],
        ]
        agent, queue_manager, _ = self._agent(
            monkeypatch, responses, config=AgentConfig(tools=["google_serper"]), tool=tool
        )
        answer = agent.run("杭州天气怎么样")
        events = _collect(queue_manager, "task-agent")

        assert answer == "根据搜索结果，杭州今天晴"
        tool.invoke.assert_called_with({"query": "杭州天气"})
        sequence = [event.event for event in events]
        assert sequence == [
            EventType.AGENT_THOUGHT,
            EventType.AGENT_ACTION,
            EventType.AGENT_MESSAGE,
            EventType.AGENT_END,
        ]
        thought = events[0]
        assert thought.tool == "google_serper"
        assert thought.tool_label == "谷歌搜索"
        assert thought.tool_input == {"query": "杭州天气"}
        action = events[1]
        assert action.observation == "杭州今天晴，25 度"
        assert action.message, "行动事件要带上本步使用的消息列表"

    def test_dataset_tool_publishes_retrieval_event(self, monkeypatch):
        tool = _fake_tool()
        tool.name = "dataset_retrieval_tool"
        responses = [
            [
                AIMessageChunk(
                    content="",
                    tool_calls=[
                        {
                            "name": "dataset_retrieval_tool",
                            "args": {"query": "报销标准"},
                            "id": "call_1",
                            "type": "tool_call",
                        }
                    ],
                )
            ],
            [AIMessageChunk(content="已找到")],
        ]
        agent, queue_manager, _ = self._agent(
            monkeypatch, responses, config=AgentConfig(tools=["dataset_retrieval_tool"]), tool=tool
        )
        agent.run("报销标准是多少")
        events = _collect(queue_manager, "task-agent")
        assert EventType.DATASET_RETRIEVAL in [event.event for event in events]

    def test_missing_tool_publishes_observation(self, monkeypatch):
        responses = [
            [
                AIMessageChunk(
                    content="",
                    tool_calls=[
                        {
                            "name": "not_installed",
                            "args": {},
                            "id": "call_1",
                            "type": "tool_call",
                        }
                    ],
                )
            ],
            [AIMessageChunk(content="这个工具目前没有")],
        ]
        # 提供商里没有任何工具实例
        agent, queue_manager, _ = self._agent(
            monkeypatch, responses, config=AgentConfig(tools=["not_installed"])
        )
        agent.run("调用不存在的工具")
        events = _collect(queue_manager, "task-agent")
        action = [event for event in events if event.event == EventType.AGENT_ACTION][0]
        assert "未找到工具 not_installed" in action.observation

    def test_long_term_memory_recall_event(self, monkeypatch):
        agent, queue_manager, model = self._agent(
            monkeypatch,
            [[AIMessageChunk(content="好的")]],
            config=AgentConfig(enable_long_term_memory=True),
        )
        agent.run("继续", long_term_memory="用户计划下周去杭州")
        events = _collect(queue_manager, "task-agent")

        assert events[0].event == EventType.LONG_TERM_MEMORY_RECALL
        assert events[0].thought == "用户计划下周去杭州"
        # 摘要被注入成系统消息，模型才看得到长期记忆
        sent = model.stream.call_args[0][0]
        assert any("用户计划下周去杭州" in str(item.content) for item in sent)

    def test_disabled_long_term_memory_emits_no_recall_event(self, monkeypatch):
        agent, queue_manager, _ = self._agent(
            monkeypatch, [[AIMessageChunk(content="好的")]]
        )
        agent.run("继续", long_term_memory="用户计划下周去杭州")
        events = _collect(queue_manager, "task-agent")
        assert [event.event for event in events] == [
            EventType.AGENT_MESSAGE,
            EventType.AGENT_END,
        ]

    def test_stopped_task_emits_stop_event(self, monkeypatch):
        agent, queue_manager, model = self._agent(
            monkeypatch, [[AIMessageChunk(content="不该被产出")]]
        )
        queue_manager.publish(
            "task-agent", AgentEventEntity(event=EventType.PING), PublishFrom.STOP
        )
        answer = agent.run("随便问点什么")
        events = _collect(queue_manager, "task-agent")

        assert answer == ""
        # 已停止的任务不再请求模型
        assert model.stream.called is False
        assert [event.event for event in events] == [
            EventType.PING,
            EventType.STOP,
            EventType.AGENT_END,
        ]

    def test_model_failure_publishes_error_event(self, monkeypatch):
        queue_manager = AgentQueueManager()
        agent = FunctionCallAgent(
            provider_manager=_fake_provider_manager(),
            queue_manager=queue_manager,
            task_id="task-error",
            config=AgentConfig(),
        )
        model = MagicMock()
        model.bind_tools.return_value = model
        model.stream.side_effect = RuntimeError("模型不可用")
        monkeypatch.setattr(agent_module, "ChatOpenAI", lambda **kwargs: model)

        assert agent.run("触发异常") == ""
        events = _collect(queue_manager, "task-error")
        assert events[-1].event == EventType.ERROR
        assert "模型不可用" in events[-1].answer

    def test_recursion_limit_is_passed_to_graph(self, monkeypatch):
        agent, _, _ = self._agent(monkeypatch, [[AIMessageChunk(content="好的")]])
        # 默认限制存在，防止工具循环把图跑飞
        assert agent.recursion_limit == agent_module.DEFAULT_RECURSION_LIMIT


class TestAgentDebugAPI:
    """GET /app/agent_debug：SSE 输出与会话数据持久化。"""

    @pytest.fixture(autouse=True)
    def clean_agent_data(self, app_context):
        """接口用例真实写库，前后都按会话名前缀清理，保证可重复执行。"""

        def purge():
            conversation_ids = [
                str(row[0])
                for row in db.session.query(Conversation.id)
                .filter(Conversation.name.like(f"{DEBUG_CONVERSATION_PREFIX}%"))
                .all()
            ]
            if not conversation_ids:
                return
            with db.auto_commit():
                db.session.query(MessageAgentThought).filter(
                    MessageAgentThought.conversation_id.in_(conversation_ids)
                ).delete(synchronize_session=False)
                db.session.query(Message).filter(
                    Message.conversation_id.in_(conversation_ids)
                ).delete(synchronize_session=False)
                db.session.query(Conversation).filter(
                    Conversation.id.in_(conversation_ids)
                ).delete(synchronize_session=False)

        purge()
        yield
        purge()

    @pytest.fixture(autouse=True)
    def mocked_dependencies(self, monkeypatch):
        """工具与摘要都换成假的，测试不联网也不花 token。"""
        tool = _fake_tool()
        provider_manager = inject.instance(BuiltinProviderManager)
        monkeypatch.setattr(
            provider_manager, "get_providers", lambda: [_fake_provider(tool=tool)]
        )
        # autoparams 装饰后类名是包装函数，要打补丁得拿容器里的实例
        message_processor = inject.instance(MessageProcessor)
        monkeypatch.setattr(
            message_processor,
            "generate_memory_summary",
            lambda human_message, ai_message, original_summary="": "合并后的摘要",
        )
        self.tool = tool

    def _request(self, client, query, **extra):
        """中文查询走 query_string 传参，避免命令行编码问题。"""
        return client.get("/app/agent_debug", query_string={"query": query, **extra})

    def _conversation(self, query):
        db.session.expire_all()
        conversation = (
            db.session.query(Conversation)
            .filter(Conversation.name == query[:30])
            .first()
        )
        assert conversation is not None
        return conversation

    def _wait_message(self, conversation_id, query, timeout=10.0):
        """等待后台线程回写消息，避免断言抢跑。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            # 回写发生在另一个线程的会话里，要让本线程的 session 重新取数据
            db.session.expire_all()
            row = (
                db.session.query(Message)
                .filter(
                    Message.conversation_id == conversation_id,
                    Message.query == query,
                )
                .first()
            )
            if row is not None and row.status in (
                MESSAGE_STATUS_COMPLETED,
                MESSAGE_STATUS_ERROR,
            ):
                return row
            time.sleep(0.05)
        raise AssertionError("后台线程没有及时回写消息状态")

    def _events(self, raw: bytes) -> list[dict]:
        """解析 SSE 帧，心跳不参与业务断言。"""
        events = []
        for frame in raw.decode("utf-8").split("\n\n"):
            frame = frame.strip()
            if frame.startswith("data: "):
                payload = json.loads(frame[len("data: ") :])
                if payload.get("event") != EventType.PING:
                    events.append(payload)
        return events

    def test_stream_outputs_events_and_persists(self, client, monkeypatch, app_context):
        model = _fake_model(
            [
                [
                    AIMessageChunk(
                        content="",
                        tool_calls=[
                            {
                                "name": "google_serper",
                                "args": {"query": "杭州天气"},
                                "id": "call_1",
                                "type": "tool_call",
                            }
                        ],
                        usage_metadata={
                            "input_tokens": 2,
                            "output_tokens": 1,
                            "total_tokens": 3,
                        },
                    )
                ],
                [
                    AIMessageChunk(
                        content="杭州今天晴",
                        usage_metadata={
                            "input_tokens": 4,
                            "output_tokens": 1,
                            "total_tokens": 5,
                        },
                    )
                ],
            ]
        )
        monkeypatch.setattr(agent_module, "ChatOpenAI", lambda **kwargs: model)

        query = f"{DEBUG_CONVERSATION_PREFIX}：工具调用流程"
        response = self._request(client, query, tools="google_serper")
        assert response.mimetype == "text/event-stream"
        events = self._events(response.get_data())
        sequence = [event["event"] for event in events]
        assert sequence == [
            EventType.AGENT_THOUGHT,
            EventType.AGENT_ACTION,
            EventType.AGENT_MESSAGE,
            EventType.AGENT_END,
        ]
        assert events[-1]["answer"] == "杭州今天晴"
        assert events[-1]["total_token_count"] == 8
        assert events[0]["task_id"] == events[-1]["task_id"]

        conversation = self._conversation(query)
        assert conversation.invoke_from == InvokeFrom.DEBUGGER
        message = self._wait_message(conversation.id, query)
        assert message.query == query
        assert message.answer == "杭州今天晴"
        assert message.status == MESSAGE_STATUS_COMPLETED
        assert message.total_token_count == 8
        assert message.latency > 0
        # 思考与行动两步落到 message_agent_thought，顺序按 position 递增
        thoughts = (
            db.session.query(MessageAgentThought)
            .filter(MessageAgentThought.message_id == message.id)
            .order_by(MessageAgentThought.position)
            .all()
        )
        assert [row.event for row in thoughts] == [
            EventType.AGENT_THOUGHT,
            EventType.AGENT_ACTION,
        ]
        assert [row.position for row in thoughts] == [1, 2]
        assert thoughts[0].tool == "google_serper"
        assert thoughts[0].tool_label == "谷歌搜索"
        assert thoughts[0].tool_input == {"query": "杭州天气"}
        assert thoughts[1].observation == "杭州今天晴，25 度"

    def test_config_prompt_is_used(self, client, monkeypatch, app_context):
        model = _fake_model([[AIMessageChunk(content="收到")]])
        monkeypatch.setattr(agent_module, "ChatOpenAI", lambda **kwargs: model)

        query = f"{DEBUG_CONVERSATION_PREFIX}：提示词配置"
        response = self._request(
            client, query, system_prompt="你是一个天气助手", preset_prompt="回答要简短"
        )
        assert self._events(response.get_data())[-1]["answer"] == "收到"
        sent = model.stream.call_args[0][0]
        assert "你是一个天气助手" in sent[0].content
        assert "回答要简短" in sent[0].content

    def test_long_term_memory_recalled_and_refreshed(
        self, client, monkeypatch, app_context
    ):
        conversation = Conversation(
            app_id=TEST_ACCOUNT_ID,
            name=f"{DEBUG_CONVERSATION_PREFIX}：历史会话",
            summary="用户计划下周去杭州",
            created_by=TEST_ACCOUNT_ID,
        )
        with db.auto_commit():
            db.session.add(conversation)
            db.session.flush()
        # 会话主键是插入时才生成的 UUID，必须先落库再挂消息
        old_message = Message(
            app_id=TEST_ACCOUNT_ID,
            conversation_id=conversation.id,
            query="上一轮问题",
            answer="上一轮回答",
            status=MESSAGE_STATUS_COMPLETED,
            created_by=TEST_ACCOUNT_ID,
        )
        with db.auto_commit():
            db.session.add(old_message)
        conversation_id = str(conversation.id)

        model = _fake_model([[AIMessageChunk(content="好的，帮你安排")]])
        monkeypatch.setattr(agent_module, "ChatOpenAI", lambda **kwargs: model)

        query = f"{DEBUG_CONVERSATION_PREFIX}：改成两天"
        response = self._request(
            client,
            query,
            conversation_id=conversation_id,
            enable_long_term_memory="true",
        )
        events = self._events(response.get_data())
        assert events[0]["event"] == EventType.LONG_TERM_MEMORY_RECALL
        assert events[0]["thought"] == "用户计划下周去杭州"
        # 短期记忆带上上一轮问答
        assert any(item["content"] == "上一轮回答" for item in events[0]["message"])

        message = self._wait_message(conversation_id, query)
        assert message.answer == "好的，帮你安排"
        # 复用同一条会话，不会按新问题名再建一条
        db.session.expire_all()
        assert (
            db.session.query(Conversation)
            .filter(Conversation.name == query[:30])
            .first()
            is None
        )
        deadline = time.monotonic() + 10
        summary = ""
        while time.monotonic() < deadline:
            db.session.expire_all()
            summary = db.session.get(Conversation, conversation_id).summary
            if summary == "合并后的摘要":
                break
            time.sleep(0.05)
        assert summary == "合并后的摘要"

    def test_missing_query_returns_validate_error(self, client):
        body = client.get("/app/agent_debug").get_json()
        assert body["code"] == HttpCode.VALIDATE_ERROR.value
        assert "query" in body["message"]

    def test_invalid_app_id_returns_validate_error(self, client):
        body = client.get(
            "/app/agent_debug",
            query_string={"query": "随便问问", "app_id": "not-a-uuid"},
        ).get_json()
        assert body["code"] == HttpCode.VALIDATE_ERROR.value
        assert "app_id" in body["message"]

    def test_model_failure_marks_message_error(self, client, monkeypatch, app_context):
        model = MagicMock()
        model.bind_tools.return_value = model
        model.stream.side_effect = RuntimeError("模型炸了")
        monkeypatch.setattr(agent_module, "ChatOpenAI", lambda **kwargs: model)

        query = f"{DEBUG_CONVERSATION_PREFIX}：模型异常"
        response = self._request(client, query, llm="missing-model")
        events = self._events(response.get_data())
        assert events[-1]["event"] == EventType.ERROR
        assert "模型炸了" in events[-1]["answer"]

        conversation = self._conversation(query)
        message = self._wait_message(conversation.id, query)
        assert message.status == MESSAGE_STATUS_ERROR
        assert "模型炸了" in message.error
        assert message.answer == ""


__all__: list = []
