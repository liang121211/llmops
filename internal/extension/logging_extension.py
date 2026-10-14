import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from flask import Flask


def init_logging(app: Flask) -> None:
    """按 .env 里的 LOGGING_* 配置初始化滚动日志。

    debug 模式下同时挂控制台处理器，方便开发时直接看到输出；
    非 debug 模式只写文件，避免生产环境刷屏。
    """
    config = app.config
    level_name = str(config.get("LOGGING_LEVEL", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)
    log_path = Path(str(config.get("LOGGING_PATH", "./storage/logs/app.log")))
    encoding = str(config.get("LOGGING_ENCODING", "utf-8"))
    formatter_str = str(
        config.get(
            "LOGGING_FORMATTER",
            "[%(asctime)s.%(msecs)03d] %(filename)s -> %(funcName)s "
            "line:%(lineno)d [%(levelname)s]: %(message)s",
        )
    )
    when = str(config.get("LOGGING_TIME_ROTATING_WHEN", "midnight"))
    interval = int(config.get("LOGGING_TIME_ROTATING_INTERVAL", 1))
    backup_count = int(config.get("LOGGING_TIME_ROTATING_BACKUP_COUNT", 30))

    # 日志目录不存在时自动创建，避免首次启动就报错
    log_path.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(formatter_str)

    file_handler = TimedRotatingFileHandler(
        filename=str(log_path),
        when=when,
        interval=interval,
        backupCount=backup_count,
        encoding=encoding,
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    # 重复调用 init_logging 时不要叠加 handler
    if not any(isinstance(h, TimedRotatingFileHandler) for h in root_logger.handlers):
        root_logger.addHandler(file_handler)

    if config.get("DEBUG"):
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(level)
        # 只排除完全相同的 StreamHandler，不排除子类（如 pytest 的 LogCaptureHandler）
        if not any(type(h) is logging.StreamHandler for h in root_logger.handlers):
            root_logger.addHandler(console_handler)


__all__ = ["init_logging"]
