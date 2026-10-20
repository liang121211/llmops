import inject
from flask import Flask
from flask_login import LoginManager

from internal.middleware.login_middleware import register_login_middleware
from internal.model import Account
from internal.service.account_service import AccountService


def init_login(app: Flask) -> LoginManager:
    """初始化 Flask-Login 登录管理器，供后续用户认证与授权使用。

    Flask-Login 会把管理器挂到 app.login_manager 上，
    这里同时返回实例，方便调用方直接持有。
    """
    login_manager = LoginManager()
    login_manager.init_app(app)
    # 管理端用 Bearer 凭证访问、不依赖浏览器会话，关闭会话保护避免每个请求改写 session
    login_manager.session_protection = "anonymous"

    account_service = inject.instance(AccountService)

    @login_manager.user_loader
    def _load_user_from_session(account_id: str) -> Account | None:
        """会话里只存账号 id，按 id 取回帐号对象。"""
        return account_service.get_account(account_id)

    # 请求加载器由登录中间件提供，负责判断蓝图并解析 JWT
    register_login_middleware(login_manager)
    return login_manager


__all__ = ["init_login"]
