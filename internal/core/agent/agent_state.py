from langchain_core.messages import BaseMessage
from langgraph.graph import MessagesState


class AgentState(MessagesState):
    """智能体图状态。

    messages 由 MessagesState 提供（LangGraph 会自动累加），这里额外带上
    短期记忆 history 和长期记忆 long_term_memory 两个通道。
    """

    # 短期记忆：本次会话之前的消息列表
    history: list[BaseMessage]
    # 长期记忆：历次对话压缩后的摘要
    long_term_memory: str


__all__ = ["AgentState"]
