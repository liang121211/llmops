"""Agent 队列管理器。

事件本身走进程内 Queue（生产者=图执行线程，消费者=SSE 监听协程），
Redis 只保存任务的基本状态：是否已经开始、是否已经停止运行，
这样多进程部署时其他节点也能通过状态键判断该任务是否还在跑。
缓存键命名：
- agent:task:<task_id>:started   任务已开始
- agent:task:<task_id>:stopped   任务已停止
"""

import logging
import threading
import time
from collections.abc import Generator
from dataclasses import dataclass, field
from queue import Empty, Queue

from flask import current_app

from internal.core.agent.agent_event import AgentEventEntity
from internal.entity import (
    AGENT_TASK_STATUS_TTL,
    DEFAULT_HEARTBEAT_INTERVAL,
    DEFAULT_LISTEN_TIMEOUT,
    DEFAULT_POLL_INTERVAL,
    EventType,
    PublishFrom,
)

logger = logging.getLogger(__name__)

# 停止监听的标记：队列里取到 None 表示没有更多事件
STOP_FLAG = None


def agent_task_started_key(task_id) -> str:
    """任务已开始状态键。"""
    return f"agent:task:{task_id}:started"


def agent_task_stopped_key(task_id) -> str:
    """任务已停止状态键。"""
    return f"agent:task:{task_id}:stopped"


@dataclass
class AgentQueueManager:
    """按 task_id 维护队列，并提供发布/监听/停止三个动作。"""

    _queues: dict = field(default_factory=dict)
    # Redis 不可用时用进程内集合兜底，保证同进程的停止语义仍然生效
    _started: set = field(default_factory=set)
    _stopped: set = field(default_factory=set)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _client: object = None

    def get_queue(self, task_id) -> Queue:
        """取该任务的队列，不存在则创建。"""
        with self._lock:
            queue = self._queues.get(task_id)
            if queue is None:
                queue = Queue()
                self._queues[task_id] = queue
            return queue

    def publish(
        self,
        task_id: str,
        event: AgentEventEntity,
        publish_from: str = PublishFrom.NORMAL,
    ) -> AgentEventEntity:
        """发布一条事件，并记录任务已经开始。"""
        event.task_id = task_id
        if publish_from == PublishFrom.STOP:
            self.mark_stopped(task_id)
        self._set_status(agent_task_started_key(task_id), task_id, self._started)
        self.get_queue(task_id).put(event)
        return event

    def stop_listen(self, task_id: str) -> None:
        """停止监听：写入停止状态并用 None 标记结束队列。"""
        self.mark_stopped(task_id)
        self.get_queue(task_id).put(STOP_FLAG)

    def listen(
        self,
        task_id: str,
        timeout: float = DEFAULT_LISTEN_TIMEOUT,
        heartbeat_interval: float = DEFAULT_HEARTBEAT_INTERVAL,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
    ) -> Generator[AgentEventEntity, None, None]:
        """监听任务事件，队列持续为空时按心跳发 ping，超过 timeout 发 timeout。"""
        queue = self.get_queue(task_id)
        started_at = time.monotonic()
        last_ping_at = started_at
        while True:
            try:
                item = queue.get(timeout=poll_interval)
            except Empty:
                now = time.monotonic()
                if now - started_at >= timeout:
                    # 超时：通知前端本次监听结束，同时清掉队列
                    yield self._build_status_event(task_id, EventType.TIMEOUT)
                    self.clear(task_id)
                    return
                if now - last_ping_at >= heartbeat_interval:
                    last_ping_at = now
                    yield self._build_status_event(task_id, EventType.PING)
                continue
            if item is STOP_FLAG:
                self.clear(task_id)
                return
            last_ping_at = time.monotonic()
            yield item

    def is_started(self, task_id: str) -> bool:
        """任务是否已经开始。"""
        return self._read_status(agent_task_started_key(task_id), task_id, self._started)

    def is_stopped(self, task_id: str) -> bool:
        """任务是否已被停止，图节点每轮都会检查该状态。"""
        return self._read_status(agent_task_stopped_key(task_id), task_id, self._stopped)

    def mark_stopped(self, task_id: str) -> None:
        """写入停止状态。"""
        self._set_status(agent_task_stopped_key(task_id), task_id, self._stopped)

    def clear(self, task_id: str) -> None:
        """清理队列与进程内状态，Redis 状态交给 TTL 自然过期。"""
        with self._lock:
            self._queues.pop(task_id, None)
            self._started.discard(task_id)
            self._stopped.discard(task_id)

    def _build_status_event(self, task_id: str, event_type: str) -> AgentEventEntity:
        """构造 ping/timeout 这类不带内容的状态事件。"""
        return AgentEventEntity(task_id=task_id, event=event_type)

    def _redis_client(self):
        """取 Redis 客户端，优先用当前应用上下文里的实例并缓存一份。"""
        if self._client is not None:
            return self._client
        try:
            client = current_app.extensions.get("redis")
        except RuntimeError:
            client = None
        if client is not None:
            self._client = client
        return client

    def _set_status(self, key: str, task_id: str, local: set) -> None:
        """写任务状态：本地集合先记一份，Redis 写失败不影响执行。"""
        local.add(task_id)
        client = self._redis_client()
        if client is None:
            return
        try:
            client.set(key, "1", ex=AGENT_TASK_STATUS_TTL)
        except Exception as error:
            logger.warning("写入 Agent 任务状态失败：%s（%s）", key, error)

    def _read_status(self, key: str, task_id: str, local: set) -> bool:
        """读任务状态：Redis 优先，读不到时退回进程内集合。"""
        client = self._redis_client()
        if client is not None:
            try:
                if client.get(key):
                    return True
            except Exception as error:
                logger.warning("读取 Agent 任务状态失败：%s（%s）", key, error)
        return task_id in local


__all__ = [
    "AgentQueueManager",
    "STOP_FLAG",
    "agent_task_started_key",
    "agent_task_stopped_key",
]
