import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import inject
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from internal.core.agent.agent_config import AgentConfig
from internal.core.agent.agent_event import AgentEventEntity
from internal.core.agent.agent_state import AgentState
from internal.core.agent.base_agent import BaseAgent
from internal.core.agent.queue_manager import AgentQueueManager
from internal.core.tools.builtin_tools import BuiltinProviderManager
from internal.entity import EventType, PublishFrom

# 图节点执行次数上限，避免工具循环停不下来
DEFAULT_RECURSION_LIMIT = 12
# 请求没点名工具时默认开放的内置插件：联网搜索 + 天气查询
DEFAULT_AGENT_TOOLS = ("google_serper", "gaode_weather")


@inject.autoparams("provider_manager", "queue_manager")
@dataclass
class FunctionCallAgent(BaseAgent):
    """函数调用智能体：长期记忆召回 -> 大模型 -> 工具 -> 大模型，由路由函数决定流向。"""

    provider_manager: BuiltinProviderManager
    queue_manager: AgentQueueManager
    # 每次执行单独构造实例，task_id/config 由调用方给出
    task_id: str = ""
    config: AgentConfig = field(default_factory=AgentConfig)
    # 事件回调，服务层用它把事件同步落库
    on_event: Callable[[AgentEventEntity], None] | None = None
    # 图节点执行次数上限
    recursion_limit: int = DEFAULT_RECURSION_LIMIT

    def run(
        self,
        query: str,
        history: list | None = None,
        long_term_memory: str = "",
    ) -> str:
        """执行一次智能体调用，返回最终答案，过程事件写入队列。"""
        history = history or []
        started_at = time.monotonic()
        self._token_count = 0
        answer = ""
        initial_state: dict[str, Any] = {
            "messages": self._initial_messages(query, history),
            "history": history,
            "long_term_memory": long_term_memory,
        }
        try:
            final_state = self._build_graph().invoke(
                initial_state, config={"recursion_limit": self.recursion_limit}
            )
            answer = self._last_ai_content(final_state)
            self._publish(
                AgentEventEntity(
                    task_id=self.task_id,
                    event=EventType.AGENT_END,
                    answer=answer,
                    total_token_count=self._token_count,
                    latency=self._latency(started_at),
                )
            )
        except Exception as error:
            self._publish(
                AgentEventEntity(
                    task_id=self.task_id,
                    event=EventType.ERROR,
                    answer=str(error),
                    total_token_count=self._token_count,
                    latency=self._latency(started_at),
                ),
                PublishFrom.ERROR,
            )
        finally:
            # 无论成功还是失败都要投放停止标记，监听端才能收尾
            self.queue_manager.stop_listen(self.task_id)
        return answer

    def _build_graph(self):
        """构造 LangGraph 图：三个业务节点 + 一个路由函数。"""
        graph = StateGraph(AgentState)
        graph.add_node("memory", self._memory_node)
        graph.add_node("llm", self._llm_node)
        graph.add_node("tool", self._tool_node)
        graph.add_edge(START, "memory")
        graph.add_edge("memory", "llm")
        # 路由节点：只用「起始节点 + 路由函数」，路由函数直接返回下一个节点名
        graph.add_conditional_edges("llm", self._route)
        graph.add_conditional_edges("tool", self._route)
        return graph.compile()

    def _route(self, state: AgentState) -> str:
        """条件路由：模型要调工具去工具节点，工具结果回模型，否则结束。"""
        if self.queue_manager.is_stopped(self.task_id):
            return END
        messages = state.get("messages") or []
        if not messages:
            return END
        last = messages[-1]
        if isinstance(last, ToolMessage):
            return "llm"
        if isinstance(last, AIMessage) and (last.tool_calls or []):
            return "tool"
        return END

    def _memory_node(self, state: AgentState) -> dict:
        """长期记忆召回节点：把摘要注入成一条系统消息。"""
        memory = str(state.get("long_term_memory") or "")
        if not (self.config.enable_long_term_memory and memory):
            return {"messages": []}
        self._publish(
            AgentEventEntity(
                task_id=self.task_id,
                event=EventType.LONG_TERM_MEMORY_RECALL,
                thought=memory,
                message=self._dump_messages(state),
            )
        )
        return {
            "messages": [
                SystemMessage(content=f"长期记忆（历史对话摘要）：{memory}")
            ]
        }

    def _llm_node(self, state: AgentState) -> dict:
        """大模型节点：流式产出消息，需要工具时先播报思考。"""
        if self.queue_manager.is_stopped(self.task_id):
            self._publish(
                AgentEventEntity(task_id=self.task_id, event=EventType.STOP),
                PublishFrom.STOP,
            )
            return {"messages": []}
        started_at = time.monotonic()
        messages = state["messages"]
        final: Any = None
        for chunk in self._model().stream(messages):
            if chunk.content:
                self._publish(
                    AgentEventEntity(
                        task_id=self.task_id,
                        event=EventType.AGENT_MESSAGE,
                        answer=str(chunk.content),
                        message=self._dump_messages(state),
                        latency=self._latency(started_at),
                    )
                )
            final = chunk if final is None else final + chunk
        if final is None:
            return {"messages": []}
        self._token_count += self._usage_tokens(final)
        for call in (final.tool_calls or []):
            self._publish(
                AgentEventEntity(
                    task_id=self.task_id,
                    event=EventType.AGENT_THOUGHT,
                    thought=f"需要调用工具 {call['name']}",
                    tool=call["name"],
                    tool_label=self._tool_label(call["name"]),
                    tool_input=dict(call.get("args") or {}),
                    message=self._dump_messages(state),
                    latency=self._latency(started_at),
                )
            )
        return {"messages": [final]}

    def _tool_node(self, state: AgentState) -> dict:
        """工具节点：执行模型请求的工具调用并回传观察结果。"""
        started_at = time.monotonic()
        last = state["messages"][-1]
        outputs: list[BaseMessage] = []
        for call in (getattr(last, "tool_calls", None) or []):
            tool = self._tools_by_name().get(call["name"])
            if tool is None:
                observation = f"未找到工具 {call['name']}"
            else:
                try:
                    observation = str(tool.invoke(call["args"]))
                except Exception as error:
                    observation = f"工具调用失败：{error}"
            event_type = (
                EventType.DATASET_RETRIEVAL
                if str(call["name"]).startswith("dataset")
                else EventType.AGENT_ACTION
            )
            self._publish(
                AgentEventEntity(
                    task_id=self.task_id,
                    event=event_type,
                    tool=call["name"],
                    tool_label=self._tool_label(call["name"]),
                    tool_input=dict(call.get("args") or {}),
                    observation=observation[:2000],
                    message=self._dump_messages(state),
                    latency=self._latency(started_at),
                )
            )
            outputs.append(
                ToolMessage(
                    content=observation,
                    tool_call_id=call.get("id"),
                    name=call["name"],
                )
            )
        return {"messages": outputs}

    def _initial_messages(self, query: str, history: list) -> list[BaseMessage]:
        """系统提示词 + 短期记忆 + 本轮问题组成初始消息。"""
        messages: list[BaseMessage] = []
        prompt = self.config.merged_prompt()
        if prompt:
            messages.append(SystemMessage(content=prompt))
        messages.extend(item for item in history if isinstance(item, BaseMessage))
        messages.append(HumanMessage(content=query))
        return messages

    def _model(self) -> ChatOpenAI:
        """按配置构造大模型，工具用原生函数调用绑定。"""
        model = ChatOpenAI(model=self.config.llm, streaming=True, temperature=0)
        tools = self._resolve_tools()
        return model.bind_tools(tools) if tools else model

    def _resolve_tools(self) -> list:
        """解析可用工具：配置里点名就按名取，没点名则用默认内置工具。"""
        names = list(self.config.tools) or list(DEFAULT_AGENT_TOOLS)
        providers = self.provider_manager.get_providers()
        tools = []
        for name in names:
            for provider in providers:
                instance = provider.get_tool_instance(name)
                if instance is not None:
                    tools.append(instance)
                    break
        return tools

    def _tools_by_name(self) -> dict:
        """工具名到实例的映射，工具节点执行时使用。"""
        return {tool.name: tool for tool in self._resolve_tools()}

    def _tool_label(self, name: str) -> str:
        """取工具的展示名，找不到时退回工具名。"""
        for provider in self.provider_manager.get_providers():
            entity = provider.get_tool_entity(name)
            if entity is not None:
                return entity.label or entity.name
        return name

    @staticmethod
    def _dump_messages(state: AgentState) -> list:
        """把当前消息列表导出成 {role, content}，便于落库和前端展示。"""
        dumped = []
        for message in state.get("messages") or []:
            role = "assistant" if isinstance(message, AIMessage) else "user"
            if isinstance(message, SystemMessage):
                role = "system"
            if isinstance(message, ToolMessage):
                role = "tool"
            dumped.append({"role": role, "content": str(message.content)})
        return dumped

    @staticmethod
    def _usage_tokens(message: Any) -> int:
        """从模型返回的 usage_metadata 里取总 token 数。"""
        usage = getattr(message, "usage_metadata", None) or {}
        if isinstance(usage, dict):
            return int(usage.get("total_tokens") or 0)
        return 0

    @staticmethod
    def _last_ai_content(state: Any) -> str:
        """取最终答案：图执行完成后最后一条 AI 消息的内容。"""
        messages = (state or {}).get("messages") or []
        for message in reversed(messages):
            if isinstance(message, AIMessage) and message.content:
                return str(message.content)
        return ""

    @staticmethod
    def _latency(started_at: float) -> float:
        """距开始时间的耗时，单位秒。"""
        return round(time.monotonic() - started_at, 4)

    def _publish(
        self,
        event: AgentEventEntity,
        publish_from: str = PublishFrom.NORMAL,
    ) -> AgentEventEntity:
        """发布事件，同时回调给服务层落库。"""
        # 先落库再入队，监听端拿到事件时数据库里已经能查到这一步
        if self.on_event is not None:
            self.on_event(event)
        self.queue_manager.publish(self.task_id, event, publish_from)
        return event


__all__ = ["DEFAULT_AGENT_TOOLS", "DEFAULT_RECURSION_LIMIT", "FunctionCallAgent"]
