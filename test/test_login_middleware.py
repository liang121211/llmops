import types
import uuid

import inject
import pytest
from flask import Blueprint, Flask
from flask_login import current_user
from sqlalchemy import delete

from config import Config
from internal.extension.login_extension import init_login
from internal.middleware.login_middleware import (
    ADMIN_BLUEPRINT,
    create_request_loader,
    register_login_middleware,
)
from internal.model import Account
from internal.service import AccountService
from pkg.oauth import generate_token
from pkg.sqlalchemy import db

# 用例邮箱前缀，结束后清理
TEST_EMAIL_PREFIX = "loader-test-"
TEST_EMAIL = f"{TEST_EMAIL_PREFIX}user@example.com"
# 管理端蓝图的探针路由
ADMIN_ROUTE = "/admin/who-am-i"
# 普通业务蓝图的探针路由
APP_ROUTE = "/app/who-am-i"
JWT_SECRET = "loader-test-secret"


class _FakeJwtConfig:
    """请求加载器只用到这三项 JWT 配置。"""

    JWT_SECRET_KEY = JWT_SECRET
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRE_DAYS = 30


@pytest.fixture(scope="module")
def login_app():
    """独立的 Flask 应用：按生产方式接入登录扩展，再挂上两个蓝图做链路验证。

    全局 app 已经处理过请求，Flask 不允许再注册蓝图，所以链路用例跑在这个
    临时应用上；它共用同一个 Config 与 SQLAlchemy 实例，凭证密钥保持一致。
    """
    test_app = Flask("login_middleware_test_app")
    test_app.config.from_object(inject.instance(Config))
    db.init_app(test_app)
    init_login(test_app)

    admin = Blueprint(ADMIN_BLUEPRINT, __name__)
    plain = Blueprint("app", __name__)

    @admin.route(ADMIN_ROUTE, methods=["GET"])
    def _admin_who_am_i():
        return {
            "authenticated": bool(current_user.is_authenticated),
            "account_id": str(current_user.id) if current_user.is_authenticated else None,
        }

    # 非管理端蓝图即使带上合法凭证也不解析，行为与业务接口保持一致
    @plain.route(APP_ROUTE, methods=["GET"])
    def _plain_who_am_i():
        return {"authenticated": bool(current_user.is_authenticated)}

    test_app.register_blueprint(admin)
    test_app.register_blueprint(plain)
    return test_app


@pytest.fixture
def login_client(login_app):
    with login_app.test_client() as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clean_accounts(app_context):
    """用例真实写库，前后各清一次测试账号。"""

    def purge():
        with db.auto_commit():
            db.session.execute(
                delete(Account).where(Account.email.like(f"{TEST_EMAIL_PREFIX}%"))
            )

    purge()
    yield
    purge()


def _fake_request(blueprint, headers):
    """构造只带蓝图名与请求头的假 request，便于单测加载器。"""
    return types.SimpleNamespace(blueprint=blueprint, headers=headers)


def _account_and_token():
    """建一个测试账号并登录，返回 (账号, JWT)。"""
    account_service = inject.instance(AccountService)
    account_service.create_account(email=TEST_EMAIL, name="加载器", password="123456")
    return account_service.login(TEST_EMAIL, "123456")


class TestRequestLoader:
    """请求加载器按蓝图判断并解析 Bearer 凭证。"""

    def test_non_admin_blueprint_skips_token(self):
        calls = []
        account_service = types.SimpleNamespace(
            get_account=lambda account_id: calls.append(account_id)
        )
        loader = create_request_loader(account_service, _FakeJwtConfig())

        account = loader(_fake_request("app", {"Authorization": "Bearer whatever"}))

        assert account is None
        # 非管理端蓝图不会碰数据库
        assert calls == []

    def test_missing_bearer_header_returns_none(self):
        loader = create_request_loader(
            types.SimpleNamespace(get_account=lambda account_id: None),
            _FakeJwtConfig(),
        )

        assert loader(_fake_request(ADMIN_BLUEPRINT, {})) is None
        assert (
            loader(_fake_request(ADMIN_BLUEPRINT, {"Authorization": "Basic abc"}))
            is None
        )

    def test_valid_token_loads_account(self):
        account = types.SimpleNamespace(id=uuid.uuid4())
        token = generate_token(account.id, JWT_SECRET)
        loader = create_request_loader(
            types.SimpleNamespace(get_account=lambda account_id: account),
            _FakeJwtConfig(),
        )

        loaded = loader(
            _fake_request(ADMIN_BLUEPRINT, {"Authorization": f"Bearer {token}"})
        )
        assert loaded is account

    def test_invalid_token_returns_none(self):
        loader = create_request_loader(
            types.SimpleNamespace(get_account=lambda account_id: object()),
            _FakeJwtConfig(),
        )

        assert (
            loader(_fake_request(ADMIN_BLUEPRINT, {"Authorization": "Bearer nope"}))
            is None
        )


class TestLoginExtension:
    """登录扩展初始化与真实请求链路。"""

    def test_login_manager_is_wired(self, login_app):
        login_manager = login_app.login_manager

        assert login_manager._user_callback is not None
        assert login_manager._request_callback is not None
        # 无会话的 Bearer 认证不需要会话保护
        assert login_manager.session_protection == "anonymous"

    def test_user_loader_returns_account_by_id(self, login_app):
        account, _ = _account_and_token()

        loaded = login_app.login_manager._user_callback(str(account.id))
        assert loaded.id == account.id
        assert login_app.login_manager._user_callback(str(uuid.uuid4())) is None

    def test_register_login_middleware_uses_request_loader(self):
        recorded = []

        class _Spy:
            def request_loader(self, callback):
                recorded.append(callback)
                return callback

        register_login_middleware(_Spy())

        assert len(recorded) == 1

    def test_anonymous_request_without_token(self, login_client):
        response = login_client.get(ADMIN_ROUTE)

        assert response.get_json() == {"authenticated": False, "account_id": None}

    def test_bearer_token_authenticates_admin_request(self, login_client):
        account, token = _account_and_token()

        body = login_client.get(
            ADMIN_ROUTE, headers={"Authorization": f"Bearer {token}"}
        ).get_json()

        assert body == {"authenticated": True, "account_id": str(account.id)}

    def test_bad_token_leaves_request_anonymous(self, login_client):
        response = login_client.get(
            ADMIN_ROUTE, headers={"Authorization": "Bearer not-a-token"}
        )

        assert response.get_json() == {"authenticated": False, "account_id": None}

    def test_other_blueprint_ignores_token(self, login_client):
        _, token = _account_and_token()

        response = login_client.get(APP_ROUTE, headers={"Authorization": f"Bearer {token}"})

        assert response.get_json() == {"authenticated": False}
