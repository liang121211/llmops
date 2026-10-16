"""Redis 分布式缓存锁。

文档禁用/启用/删除等操作走 Celery 异步任务，多 worker 并发时同一份数据
可能被同时修改；Redis 集群部署下用 SET NX PX 实现互斥锁保护关键区间。
锁键命名规则：
- lock:document_status:<document_id>   更新文档状态缓存锁
- lock:keyword_table:<dataset_id>      更新关键词表缓存锁
- lock:segment_enabled:<id>            更新片段启用状态缓存锁（文档级操作用文档 ID，片段级操作用片段 ID）
- lock:dataset_delete:<dataset_id>     删除知识库缓存锁
"""

import logging
from contextlib import contextmanager

from flask import current_app

logger = logging.getLogger(__name__)

# 锁的默认超时时间（秒），可通过 .env 的 REDIS_LOCK_TIMEOUT 覆盖
DEFAULT_LOCK_TIMEOUT = 600
# 等待他人释放锁的最长时间（秒），超时抛出异常而不是无限阻塞
DEFAULT_BLOCKING_TIMEOUT = 60


class LockAcquireError(RuntimeError):
    """在等待超时时间内没有拿到缓存锁。"""


def document_status_lock_key(document_id) -> str:
    """更新文档状态缓存锁的键名。"""
    return f"lock:document_status:{document_id}"


def keyword_table_lock_key(dataset_id) -> str:
    """更新关键词表缓存锁的键名。"""
    return f"lock:keyword_table:{dataset_id}"


def segment_enabled_lock_key(document_id) -> str:
    """更新片段启用状态缓存锁的键名。"""
    return f"lock:segment_enabled:{document_id}"


def dataset_delete_lock_key(dataset_id) -> str:
    """删除知识库缓存锁的键名。"""
    return f"lock:dataset_delete:{dataset_id}"


@contextmanager
def redis_lock(key: str, timeout: int | None = None, blocking_timeout: float | None = None):
    """在锁保护下执行代码块，退出时自动释放。

    timeout 为锁的存活时间，到期自动释放，防止持有者进程崩溃造成死锁；
    blocking_timeout 为等待锁的最长时间，超时抛出 LockAcquireError。
    """
    client = current_app.extensions.get("redis")
    if client is None:
        raise RuntimeError("Redis 扩展未初始化，无法使用缓存锁")

    # 存活时间取调用方参数 > Flask 配置 > 模块默认值
    ttl = int(timeout or current_app.config.get("REDIS_LOCK_TIMEOUT") or DEFAULT_LOCK_TIMEOUT)
    wait = DEFAULT_BLOCKING_TIMEOUT if blocking_timeout is None else float(blocking_timeout)

    lock = client.lock(key, timeout=ttl, blocking_timeout=wait)
    if not lock.acquire():
        raise LockAcquireError(f"获取缓存锁失败：{key}")
    logger.debug("已获取缓存锁：%s（ttl=%s）", key, ttl)
    try:
        yield lock
    finally:
        try:
            lock.release()
            logger.debug("已释放缓存锁：%s", key)
        except Exception as e:
            # 锁超时被他人拿走时 release 会报错，只记录日志不影响业务结果
            logger.warning("释放缓存锁 %s 异常：%s", key, e)


__all__ = [
    "DEFAULT_BLOCKING_TIMEOUT",
    "DEFAULT_LOCK_TIMEOUT",
    "LockAcquireError",
    "document_status_lock_key",
    "dataset_delete_lock_key",
    "keyword_table_lock_key",
    "redis_lock",
    "segment_enabled_lock_key",
]
