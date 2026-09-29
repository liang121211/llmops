from dataclasses import dataclass

import inject
from flask import Blueprint, Flask

from internal.handler.app_handler import AppHandler


@inject.autoparams()
@dataclass
class Router:
    """路由层，通过注入拿到控制层并挂到 Flask 蓝图上。"""

    app_handler: AppHandler

    def register_router(self, app: Flask):
        # 创建蓝图并把视图函数挂到对应路由上
        bp = Blueprint("app", __name__)
        bp.add_url_rule("/ping", view_func=self.app_handler.ping, methods=["GET"])
        bp.add_url_rule(
            "/app/chat", view_func=self.app_handler.chat, methods=["POST"]
        )
        app.register_blueprint(bp)


__all__ = ["Router"]
