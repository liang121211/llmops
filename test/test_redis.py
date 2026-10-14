import redis
from flask import Flask

from internal.extension.redis_extension import init_redis


def test_init_redis_returns_client_and_registers_extension():
    app = Flask("redis_test")
    app.config.update(
        REDIS_HOST="127.0.0.1",
        REDIS_PORT=6379,
        REDIS_USERNAME="",
        REDIS_PASSWORD="",
        REDIS_DB=0,
        REDIS_USE_SSL=False,
    )

    client = init_redis(app)

    assert isinstance(client, redis.Redis)
    assert app.extensions["redis"] is client


def test_init_redis_applies_config_values():
    app = Flask("redis_test_cfg")
    app.config.update(
        REDIS_HOST="10.0.0.1",
        REDIS_PORT=6380,
        REDIS_USERNAME="testuser",
        REDIS_PASSWORD="testpass",
        REDIS_DB=3,
        REDIS_USE_SSL=True,
    )

    client = init_redis(app)
    conn_kwargs = client.connection_pool.connection_kwargs

    assert conn_kwargs["host"] == "10.0.0.1"
    assert conn_kwargs["port"] == 6380
    assert conn_kwargs["username"] == "testuser"
    assert conn_kwargs["password"] == "testpass"
    assert conn_kwargs["db"] == 3
    # ssl 在连接池里以 connection_class 或 ssl 参数体现
    assert client.connection_pool.connection_kwargs.get("ssl") is True or \
        "SSLConnection" in type(client.connection_pool.make_connection()).__name__


def test_init_redis_empty_username_becomes_none():
    """空字符串的 username/password 应转为 None，避免 Redis 认证报错。"""
    app = Flask("redis_test_empty")
    app.config.update(
        REDIS_HOST="127.0.0.1",
        REDIS_PORT=6379,
        REDIS_USERNAME="",
        REDIS_PASSWORD="",
        REDIS_DB=0,
        REDIS_USE_SSL=False,
    )

    client = init_redis(app)
    conn_kwargs = client.connection_pool.connection_kwargs

    assert conn_kwargs.get("username") is None
    assert conn_kwargs.get("password") is None


def test_init_redis_defaults_when_keys_missing():
    """配置项缺失时使用默认值，不应抛异常。"""
    app = Flask("redis_test_defaults")
    # 不提供任何 REDIS_* 配置

    client = init_redis(app)

    assert isinstance(client, redis.Redis)
    conn_kwargs = client.connection_pool.connection_kwargs
    assert conn_kwargs["host"] == "127.0.0.1"
    assert conn_kwargs["port"] == 6379
    assert conn_kwargs["db"] == 0
