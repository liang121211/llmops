from flask import Flask
from flask_weaviate import FlaskWeaviate

_weaviate = FlaskWeaviate()


def init_weaviate(app: Flask) -> FlaskWeaviate:
    """初始化 Weaviate 客户端并挂到 Flask 扩展上。"""
    _weaviate.init_app(app)
    app.extensions["weaviate"] = _weaviate
    return _weaviate


def get_weaviate() -> FlaskWeaviate:
    """获取全局 Weaviate 扩展实例。"""
    return _weaviate


__all__ = ["init_weaviate", "get_weaviate"]
