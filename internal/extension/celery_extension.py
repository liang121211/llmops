from celery import Celery, Task
from flask import Flask


class FlaskTask(Task):
    """Celery 任务基类，确保任务在 Flask 应用上下文中执行。

    worker 进程没有请求上下文，但业务代码可能依赖 current_app / db.session，
    把 app context 包进 __call__ 就能让所有继承此类的任务安全使用 Flask 资源。
    """

    _flask_app: Flask | None = None

    def __call__(self, *args, **kwargs):
        if self._flask_app is not None:
            with self._flask_app.app_context():
                return super().__call__(*args, **kwargs)
        return super().__call__(*args, **kwargs)


def init_celery(app: Flask) -> Celery:
    """按 .env 里的 CELERY_* / REDIS_* 配置初始化 Celery 并挂到 app 上。

    broker 与 result_backend 共用同一个 Redis 实例的不同 DB；
    FlaskTask 被设为默认任务基类，后续定义的 @celery.task 自动继承上下文能力。
    """
    config = app.config
    redis_host = str(config.get("REDIS_HOST", "127.0.0.1"))
    redis_port = int(config.get("REDIS_PORT", 6379))
    redis_password = str(config.get("REDIS_PASSWORD", "")) or None
    redis_username = str(config.get("REDIS_USERNAME", "")) or None
    redis_ssl = str(config.get("REDIS_USE_SSL", "false")).lower() == "true"
    broker_db = int(config.get("CELERY_BROKER_DB", 1))
    backend_db = int(config.get("CELERY_RESULT_BACKEND_DB", 1))

    scheme = "rediss" if redis_ssl else "redis"
    auth = ""
    if redis_username and redis_password:
        auth = f"{redis_username}:{redis_password}@"
    elif redis_password:
        auth = f":{redis_password}@"
    base_url = f"{scheme}://{auth}{redis_host}:{redis_port}"

    celery = Celery(
        app.import_name,
        broker=f"{base_url}/{broker_db}",
        backend=f"{base_url}/{backend_db}",
    )
    celery.conf.update(
        task_ignore_result=bool(config.get("CELERY_TASK_IGNORE_RESULT", False)),
        result_expires=int(config.get("CELERY_RESULT_EXPIRES", 3600)),
        broker_connection_retry_on_startup=bool(
            config.get("CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP", False)
        ),
        # 把 FlaskTask 设为默认基类，所有 @celery.task 自动获得 app context
        task_default_base=FlaskTask,
    )
    # 让 FlaskTask 能拿到 app 实例
    FlaskTask._flask_app = app

    # 把 celery 挂到 app.extensions，方便其他地方通过 current_app 获取
    app.extensions["celery"] = celery
    return celery


__all__ = ["FlaskTask", "init_celery"]
