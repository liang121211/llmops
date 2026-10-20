import inject
from flask import Request
from flask_login import LoginManager

from config import Config
from internal.model import Account
from internal.service.account_service import AccountService
from pkg.oauth import get_account_id_from_token

# 只有管理端蓝图的接口需要登录态，其余蓝图（如 app 调试接口）不解析凭证
ADMIN_BLUEPRINT = "admin"
# 凭证放在 Authorization 头，格式为 Bearer <jwt>
BEARER_PREFIX = "Bearer "


def create_request_loader(
    account_service: AccountService, config: Config
):
    """构造登录管理器的请求加载器：按蓝图判断并解析 Bearer 凭证。"""

    def _load_user_from_request(request: Request) -> Account | None:
        # 请求路由到的蓝图不是管理端，直接当作匿名访问
        if request.blueprint != ADMIN_BLUEPRINT:
            return None
        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith(BEARER_PREFIX):
            return None
        token = authorization[len(BEARER_PREFIX) :].strip()
        account_id = get_account_id_from_token(
            token, str(config.JWT_SECRET_KEY), str(config.JWT_ALGORITHM)
        )
        if account_id is None:
            return None
        return account_service.get_account(account_id)

    return _load_user_from_request


def register_login_middleware(login_manager: LoginManager) -> None:
    """把请求加载器接到登录管理器上，依赖从注入容器取。"""
    # request_loader 是注册回调的方法，直接赋值不会写进 _request_callback
    login_manager.request_loader(
        create_request_loader(inject.instance(AccountService), inject.instance(Config))
    )


__all__ = ["ADMIN_BLUEPRINT", "create_request_loader", "register_login_middleware"]
