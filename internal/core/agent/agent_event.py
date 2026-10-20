from dataclasses import asdict, dataclass, field
from uuid import uuid4

from internal.entity import EventType


@dataclass
class AgentEventEntity:
    """队列消息实体，一次智能体执行会连续产出多条该实体。"""

    id: str = field(default_factory=lambda: str(uuid4()))
    task_id: str = ""
    # 事件类型，取值见 internal.entity.EventType
    event: str = EventType.AGENT_MESSAGE
    # 思考内容与工具观察结果
    thought: str = ""
    observation: str = ""
    # 工具名与工具入参
    tool: str = ""
    tool_label: str = ""
    tool_input: dict = field(default_factory=dict)
    # 本步推理使用到的消息列表（角色+内容）
    message: list = field(default_factory=list)
    message_token_count: int = 0
    message_unit_price: float = 0
    message_price_unit: float = 0
    # 最终回复内容及其计费信息
    answer: str = ""
    answer_token_count: int = 0
    answer_unit_price: float = 0
    answer_price_unit: float = 0
    total_token_count: int = 0
    total_price: float = 0
    # 本步执行耗时（秒）
    latency: float = 0

    def to_dict(self) -> dict:
        """转成可 JSON 序列化的字典，SSE 帧与落库都用它。"""
        return asdict(self)


__all__ = ["AgentEventEntity"]
