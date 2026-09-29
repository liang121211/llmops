import inject

from internal.handler.app_handler import AppHandler
from internal.router.router import Router


def _configure(binder):
    binder.bind_to_constructor(AppHandler, AppHandler)
    binder.bind_to_constructor(Router, Router)


def init_inject():
    """配置 inject 绑定。"""
    inject.clear_and_configure(_configure)


__all__ = ["init_inject"]
