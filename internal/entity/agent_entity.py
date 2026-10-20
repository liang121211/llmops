"""工具调用 Agent 的状态常量与事件类型。"""


class PublishFrom:
    """事件发布来源状态。"""

    # 正常发布
    NORMAL = "normal"
    # 用户主动停止
    STOP = "stop"
    # 执行出错
    ERROR = "error"


class InvokeFrom:
    """调用来源。"""

    DEBUGGER = "debugger"
    WEBAPP = "webapp"
    END_USER = "end_user"


class EventType:
    """队列事件类型。"""

    # 长期记忆召回
    LONG_TERM_MEMORY_RECALL = "long_term_memory_recall"
    # 智能体思考（按前后端约定保留该拼写）
    AGENT_THOUGHT = "agent_though"
    # 智能体消息（AI 回复内容）
    AGENT_MESSAGE = "agent_message"
    # 智能体行动（工具调用结果）
    AGENT_ACTION = "agent_action"
    # 知识库检索
    DATASET_RETRIEVAL = "dataset_retrieval"
    # 智能体结束
    AGENT_END = "agent_end"
    # 停止
    STOP = "stop"
    # 错误
    ERROR = "error"
    # 监听超时
    TIMEOUT = "timeout"
    # 心跳
    PING = "ping"


# 监听超时时间，超过这个时长队列仍然没有结束就发 timeout 事件
DEFAULT_LISTEN_TIMEOUT = 600
# 心跳间隔，队列持续为空时每隔该时长发一次 ping
DEFAULT_HEARTBEAT_INTERVAL = 10
# 队列轮询间隔，用短超时轮询才能同时做心跳与超时判断
DEFAULT_POLL_INTERVAL = 1
# Redis 任务状态键的存活时间，防止异常退出后状态长期残留
AGENT_TASK_STATUS_TTL = 1800


__all__ = [
    "PublishFrom",
    "InvokeFrom",
    "EventType",
    "DEFAULT_LISTEN_TIMEOUT",
    "DEFAULT_HEARTBEAT_INTERVAL",
    "DEFAULT_POLL_INTERVAL",
    "AGENT_TASK_STATUS_TTL",
]
