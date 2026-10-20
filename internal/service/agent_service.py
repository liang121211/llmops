import logging
import threading
import time
import uuid
from collections.abc import Generator
from dataclasses import dataclass
from itertools import count

import inject
from flask import current_app
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from sqlalchemy import select

from internal.core.agent import (
    AgentConfig,
    AgentEventEntity,
    AgentQueueManager,
    FunctionCallAgent,
)
from internal.core.message_processor import MessageProcessor
from internal.core.tools.builtin_tools import BuiltinProviderManager
from internal.entity import (
    DEFAULT_HEARTBEAT_INTERVAL,
    DEFAULT_LISTEN_TIMEOUT,
    EventType,
    InvokeFrom,
)
from internal.model.conversation import Conversation, Message, MessageAgentThought
from pkg.sqlalchemy import SQLAlchemy

logger = logging.getLogger(__name__)

# 一次调试执行最多带出的短期记忆条数
DEFAULT_HISTORY_LIMIT = 10
# 没有指定应用时落库使用的占位 app_id（调试场景不绑定具体应用）
DEBUG_APP_ID = "00000000-0000-0000-0000-000000000000"
# 会话名称取用户问题前若干字符
CONVERSATION_NAME_LENGTH = 30
# 消息状态：正常 / 完成 / 出错
MESSAGE_STATUS_NORMAL = "normal"
MESSAGE_STATUS_COMPLETED = "completed"
MESSAGE_STATUS_ERROR = "error"


@inject.autoparams()
@dataclass
class AgentService:
    """智能体服务：编排线程执行、事件落库与 SSE 监听。"""

    db: SQLAlchemy
    provider_manager: BuiltinProviderManager
    queue_manager: AgentQueueManager
    message_processor: MessageProcessor

    def debug_stream(
        self,
        query: str,
        config: AgentConfig,
        account_id: str,
        app_id: str | None = None,
        conversation_id: str | None = None,
        invoke_from: str = InvokeFrom.DEBUGGER,
        history_limit: int = DEFAULT_HISTORY_LIMIT,
        listen_timeout: float = DEFAULT_LISTEN_TIMEOUT,
        heartbeat_interval: float = DEFAULT_HEARTBEAT_INTERVAL,
    ) -> Generator[dict, None, None]:
        """执行一次调试调用，返回事件字典生成器，供 SSE 输出。"""
        task_id = str(uuid.uuid4())
        app_id = app_id or DEBUG_APP_ID
        conversation = self._prepare_conversation(
            query=query,
            app_id=app_id,
            account_id=account_id,
            conversation_id=conversation_id,
            invoke_from=invoke_from,
        )
        history = self._load_history(conversation.id, history_limit)
        message = self._create_message(
            query=query,
            conversation=conversation,
            app_id=app_id,
            account_id=account_id,
            invoke_from=invoke_from,
            history=history,
        )
        long_term_memory = conversation.summary if config.enable_long_term_memory else ""

        agent = FunctionCallAgent(
            provider_manager=self.provider_manager,
            queue_manager=self.queue_manager,
            task_id=task_id,
            config=config,
        )
        self._start_thread(
            agent=agent,
            query=query,
            history=history,
            long_term_memory=long_term_memory,
            config=config,
            message=message,
            conversation=conversation,
            app_id=app_id,
            account_id=account_id,
            invoke_from=invoke_from,
        )
        # 队列里的实体转成字典，交给统一响应包装成 SSE 帧
        return (
            event.to_dict()
            for event in self.queue_manager.listen(
                task_id, timeout=listen_timeout, heartbeat_interval=heartbeat_interval
            )
        )

    def _prepare_conversation(
        self,
        query: str,
        app_id: str,
        account_id: str,
        conversation_id: str | None,
        invoke_from: str,
    ) -> Conversation:
        """有会话 id 就复用，没有则新建一条会话。"""
        if conversation_id:
            conversation = self.db.session.get(Conversation, conversation_id)
            if conversation is not None:
                return conversation
        conversation = Conversation(
            app_id=app_id,
            name=query[:CONVERSATION_NAME_LENGTH],
            invoke_from=invoke_from,
            created_by=account_id,
        )
        with self.db.auto_commit():
            self.db.session.add(conversation)
            self.db.session.flush()
        return conversation

    def _load_history(self, conversation_id, limit: int) -> list[BaseMessage]:
        """短期记忆：取该会话最近 limit 条问答，按时间正序还原成消息列表。"""
        stmt = (
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.status == MESSAGE_STATUS_COMPLETED,
            )
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        rows = list(self.db.session.execute(stmt).scalars().all())
        rows.reverse()
        messages: list[BaseMessage] = []
        for row in rows:
            if row.query:
                messages.append(HumanMessage(content=row.query))
            if row.answer:
                messages.append(AIMessage(content=row.answer))
        return messages

    def _create_message(
        self,
        query: str,
        conversation: Conversation,
        app_id: str,
        account_id: str,
        invoke_from: str,
        history: list[BaseMessage],
    ) -> Message:
        """先落一条消息记录，执行过程中再补齐答案与计费信息。"""
        message = Message(
            app_id=app_id,
            conversation_id=conversation.id,
            invoke_from=invoke_from,
            created_by=account_id,
            query=query,
            message=[{"role": "user", "content": query}]
            + [
                {
                    "role": "assistant"
                    if isinstance(item, AIMessage)
                    else "user",
                    "content": str(item.content),
                }
                for item in history
            ],
            status=MESSAGE_STATUS_NORMAL,
        )
        with self.db.auto_commit():
            self.db.session.add(message)
            self.db.session.flush()
        return message

    def _start_thread(
        self,
        agent: FunctionCallAgent,
        query: str,
        history: list[BaseMessage],
        long_term_memory: str,
        config: AgentConfig,
        message: Message,
        conversation: Conversation,
        app_id: str,
        account_id: str,
        invoke_from: str,
    ) -> None:
        """开启线程执行智能体，事件边产出边落库。"""
        # Flask 上下文是线程本地的，后台线程要重新进入真实 app 的上下文
        flask_app = current_app._get_current_object()
        message_id = str(message.id)
        conversation_id = str(conversation.id)
        started_at = time.monotonic()
        # 推理步骤序号，落库时按产出顺序递增
        position = count(1)
        # 记下结束/错误事件，线程结束后用它回写消息
        finished: dict = {}

        def on_event(event: AgentEventEntity) -> None:
            if event.event in (EventType.AGENT_END, EventType.ERROR):
                finished["terminal"] = event
                return
            # 思考/行动/记忆召回等过程事件写入 message_agent_thought
            if event.event == EventType.AGENT_MESSAGE:
                return
            self._persist_thought(
                event=event,
                message_id=message_id,
                conversation_id=conversation_id,
                app_id=app_id,
                account_id=account_id,
                invoke_from=invoke_from,
                position=next(position),
            )

        agent.on_event = on_event

        def produce() -> None:
            with flask_app.app_context():
                try:
                    answer = agent.run(query, history, long_term_memory)
                    self._finish_message(
                        message_id=message_id,
                        conversation_id=conversation_id,
                        answer=answer,
                        terminal=finished.get("terminal"),
                        started_at=started_at,
                        config=config,
                        query=query,
                    )
                except Exception as error:
                    logger.exception("智能体执行失败：%s", error)
                    self._mark_message_error(message_id, str(error))

        thread = threading.Thread(target=produce, daemon=True)
        thread.start()

    def _persist_thought(
        self,
        event: AgentEventEntity,
        message_id: str,
        conversation_id: str,
        app_id: str,
        account_id: str,
        invoke_from: str,
        position: int,
    ) -> None:
        """把一条过程事件写成推理步骤记录。"""
        thought = MessageAgentThought(
            id=event.id,
            app_id=app_id,
            conversation_id=conversation_id,
            message_id=message_id,
            invoke_from=invoke_from,
            created_by=account_id,
            position=position,
            event=event.event,
            thought=event.thought,
            observation=event.observation,
            tool=event.tool,
            tool_label=event.tool_label,
            tool_params=event.tool_input,
            tool_input=event.tool_input,
            message=event.message,
            message_token_count=event.message_token_count,
            message_unit_price=event.message_unit_price,
            message_price_unit=event.message_price_unit,
            answer=event.answer,
            answer_token_count=event.answer_token_count,
            answer_unit_price=event.answer_unit_price,
            answer_price_unit=event.answer_price_unit,
            total_token_count=event.total_token_count,
            total_price=event.total_price,
            latency=event.latency,
        )
        with self.db.auto_commit():
            self.db.session.add(thought)

    def _finish_message(
        self,
        message_id: str,
        conversation_id: str,
        answer: str,
        terminal: AgentEventEntity | None,
        started_at: float,
        config: AgentConfig,
        query: str,
    ) -> None:
        """回写消息的结果信息，并按需刷新会话的长期记忆摘要。"""
        is_error = terminal is not None and terminal.event == EventType.ERROR
        with self.db.auto_commit():
            message = self.db.session.get(Message, message_id)
            if message is None:
                return
            message.answer = "" if is_error else answer
            message.error = terminal.answer if is_error else ""
            message.status = (
                MESSAGE_STATUS_ERROR if is_error else MESSAGE_STATUS_COMPLETED
            )
            message.latency = (
                terminal.latency
                if terminal is not None
                else round(time.monotonic() - started_at, 4)
            )
            message.total_token_count = terminal.total_token_count if terminal else 0
            message.total_price = terminal.total_price if terminal else 0
        if is_error or not config.enable_long_term_memory:
            return
        # 开启长期记忆时把本轮问答压缩进会话摘要，供下次召回
        self._refresh_summary(conversation_id, query, answer)

    def _mark_message_error(self, message_id: str, error: str) -> None:
        """线程异常兜底，避免消息一直停在 normal。"""
        with self.db.auto_commit():
            message = self.db.session.get(Message, message_id)
            if message is None:
                return
            message.status = MESSAGE_STATUS_ERROR
            message.error = error

    def _refresh_summary(self, conversation_id: str, query: str, answer: str) -> None:
        """用摘要模型把最新一轮对话合并进会话摘要。"""
        with self.db.auto_commit():
            conversation = self.db.session.get(Conversation, conversation_id)
            if conversation is None:
                return
            conversation.summary = self.message_processor.generate_memory_summary(
                human_message=query,
                ai_message=answer,
                original_summary=conversation.summary,
            )


__all__ = ["AgentService"]
