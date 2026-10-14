from flask import Flask

from config import Config, DEFAULT_CONFIG

REQUIRED_KEYS = {
    "SECRET_KEY",
    "DEBUG",
    "HOST",
    "PORT",
    "SQLALCHEMY_DATABASE_URI",
    "SQLALCHEMY_TRACK_MODIFICATIONS",
    "MINIO_ENDPOINT",
    "MINIO_ACCESS_KEY",
    "MINIO_SECRET_KEY",
    "MINIO_BUCKET",
    "WEAVIATE_URL",
}


def test_default_config_contains_required_keys():
    assert REQUIRED_KEYS <= set(DEFAULT_CONFIG)


def test_default_config_value_types():
    assert isinstance(DEFAULT_CONFIG["SECRET_KEY"], str)
    assert DEFAULT_CONFIG["SECRET_KEY"]
    assert isinstance(DEFAULT_CONFIG["DEBUG"], bool)
    assert isinstance(DEFAULT_CONFIG["HOST"], str)
    assert isinstance(DEFAULT_CONFIG["PORT"], int)
    assert DEFAULT_CONFIG["PORT"] > 0


def test_config_defines_only_the_constructor():
    public_members = [
        name
        for name, value in vars(Config).items()
        if callable(value) and not name.startswith("_")
    ]

    assert public_members == []


def test_config_copies_every_default_item():
    config = Config()

    for key, value in DEFAULT_CONFIG.items():
        assert getattr(config, key) == value


def test_config_hardcodes_wtf_disabled():
    assert Config().WTF_CSRF_ENABLED is False


def test_config_wtf_switch_wins_over_default_items(monkeypatch):
    monkeypatch.setitem(DEFAULT_CONFIG, "WTF_CSRF_ENABLED", True)

    assert Config().WTF_CSRF_ENABLED is False


def test_flask_loads_config_and_can_toggle_debug():
    config = Config()
    config.DEBUG = False
    app = Flask("config_test")

    app.config.from_object(config)

    assert app.config["WTF_CSRF_ENABLED"] is False
    assert app.config["DEBUG"] is False
    assert app.debug is False
    assert app.config["SECRET_KEY"] == config.SECRET_KEY
    assert app.config["PORT"] == config.PORT
