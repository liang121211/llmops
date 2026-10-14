import redis
from flask import Flask
from redis.backoff import NoBackoff
from redis.retry import Retry


def init_redis(app: Flask) -> redis.Redis:
    """按 .env 里的 REDIS_* 配置初始化 Redis 连接并挂到 app.extensions 上。

    返回 Redis 客户端实例，方便调用方直接使用；
    同时存入 app.extensions["redis"]，后续可通过 current_app.extensions 获取。
    """
    config = app.config
    client = redis.Redis(
        host=str(config.get("REDIS_HOST", "127.0.0.1")),
        port=int(config.get("REDIS_PORT", 6379)),
        username=str(config.get("REDIS_USERNAME", "")) or None,
        password=str(config.get("REDIS_PASSWORD", "")) or None,
        db=int(config.get("REDIS_DB", 0)),
        ssl=str(config.get("REDIS_USE_SSL", "false")).lower() == "true",
        decode_responses=True,
        socket_connect_timeout=3,
        retry=Retry(NoBackoff(), 0),
    )
    app.extensions["redis"] = client
    return client


__all__ = ["init_redis"]
