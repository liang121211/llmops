import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import pytest
from flask import Flask

from internal.extension.logging_extension import init_logging


@pytest.fixture
def app(tmp_path):
    """最小 Flask 应用，日志路径指向临时目录避免污染仓库。"""
    application = Flask("logging_test")
    log_file = tmp_path / "logs" / "app.log"
    application.config.update(
        DEBUG=False,
        LOGGING_LEVEL="INFO",
        LOGGING_PATH=str(log_file),
        LOGGING_ENCODING="utf-8",
        LOGGING_FORMATTER="%(levelname)s:%(message)s",
        LOGGING_TIME_ROTATING_WHEN="midnight",
        LOGGING_TIME_ROTATING_INTERVAL=1,
        LOGGING_TIME_ROTATING_BACKUP_COUNT=7,
    )
    return application


@pytest.fixture(autouse=True)
def clean_root_handlers():
    """每个用例前后清空 root logger 上全部 handler，避免 seed 或前一测试残留干扰。"""
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    yield
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()


def _our_file_handler(expected_path: str) -> TimedRotatingFileHandler | None:
    """按文件路径精确找到 init_logging 创建的 handler，避开 pytest 注入的 handler。"""
    resolved = str(Path(expected_path).resolve())
    for handler in logging.getLogger().handlers:
        if isinstance(handler, TimedRotatingFileHandler):
            if str(Path(handler.baseFilename).resolve()) == resolved:
                return handler
    return None


def _console_handlers() -> list[logging.StreamHandler]:
    """只统计 init_logging 添加的控制台 handler，排除 pytest 注入的 LogCaptureHandler。"""
    return [
        h
        for h in logging.getLogger().handlers
        if isinstance(h, logging.StreamHandler)
        and not isinstance(h, TimedRotatingFileHandler)
        and type(h).__name__ != "LogCaptureHandler"
    ]


def test_init_logging_creates_file_handler(app):
    init_logging(app)

    handler = _our_file_handler(app.config["LOGGING_PATH"])
    assert handler is not None
    assert Path(handler.baseFilename).name == "app.log"


def test_init_logging_configures_file_handler_from_config(app):
    init_logging(app)

    handler = _our_file_handler(app.config["LOGGING_PATH"])
    assert handler is not None
    assert handler.level == logging.INFO
    assert handler.backupCount == 7
    assert handler.formatter._fmt == "%(levelname)s:%(message)s"
    assert Path(handler.baseFilename).parent.is_dir()


def test_init_logging_adds_console_handler_in_debug(app):
    app.config["DEBUG"] = True

    init_logging(app)

    assert len(_console_handlers()) == 1


def test_init_logging_skips_console_handler_when_not_debug(app):
    init_logging(app)

    assert _console_handlers() == []


def test_init_logging_does_not_duplicate_handlers(app):
    init_logging(app)
    init_logging(app)

    handler = _our_file_handler(app.config["LOGGING_PATH"])
    assert handler is not None
    # 同一个路径只应有一个 TimedRotatingFileHandler
    matches = [
        h
        for h in logging.getLogger().handlers
        if isinstance(h, TimedRotatingFileHandler)
        and str(Path(h.baseFilename).resolve())
        == str(Path(app.config["LOGGING_PATH"]).resolve())
    ]
    assert len(matches) == 1


def test_init_logging_creates_log_directory(tmp_path):
    app = Flask("logging_test_dir")
    nested = tmp_path / "deep" / "nested" / "app.log"
    app.config.update(
        DEBUG=False,
        LOGGING_LEVEL="WARNING",
        LOGGING_PATH=str(nested),
        LOGGING_ENCODING="utf-8",
        LOGGING_FORMATTER="%(message)s",
        LOGGING_TIME_ROTATING_WHEN="H",
        LOGGING_TIME_ROTATING_INTERVAL=2,
        LOGGING_TIME_ROTATING_BACKUP_COUNT=3,
    )

    init_logging(app)

    assert nested.parent.is_dir()
    handler = _our_file_handler(str(nested))
    assert handler is not None
    assert handler.level == logging.WARNING
    assert handler.when == "H"
    # interval 是 TimedRotatingFileHandler 内部换算后的秒数，2 小时 = 7200 秒
    assert handler.interval == 2 * 3600
    assert handler.backupCount == 3


def test_init_logging_falls_back_to_defaults_when_keys_missing(tmp_path):
    """配置项缺失时使用默认值，不应抛异常。"""
    app = Flask("logging_test_defaults")
    log_file = tmp_path / "default.log"
    app.config.update(DEBUG=False, LOGGING_PATH=str(log_file))

    init_logging(app)

    root = logging.getLogger()
    assert root.level == logging.INFO
    handler = _our_file_handler(str(log_file))
    assert handler is not None
    assert handler.backupCount == 30
