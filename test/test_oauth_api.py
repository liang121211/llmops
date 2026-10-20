import inject
import pytest
from sqlalchemy import delete

from app.http.app import app
from internal.model import Account, AccountOAuth
from internal.pkg.response import HttpCode
from pkg.oauth import DEFAULT_EMAIL_SUFFIX, OAuth2Manager, OAuth2Provider, OAuthUserInfo
from pkg.oauth import get_account_id_from_token
from pkg.sqlalchemy import db

# 接口用例统一走 gitee 这条路由，提供商实例被桩替换，不会发出网络请求
PROVIDER_NAME = "gitee"
OPENID = "90002"
LOGIN = "api-user"
EMAIL = f"{OPENID}{LOGIN}{DEFAULT_EMAIL_SUFFIX}"
CALLBACK_URL = f"/oauth/{PROVIDER_NAME}"
AUTHORIZE_URL = f"/oauth/{PROVIDER_NAME}/authorize"


class _StubProvider(OAuth2Provider):
    """替代真实 Gitee 提供商的桩，只提供接口用例需要的固定返回值。"""

    name = PROVIDER_NAME
    label = "接口测试"
    description = "接口用例使用的桩提供商。"

    def __init__(self):
        # 跳过基类的 .env 校验，接口用例不依赖真实第三方配置
        self.access_token = "api-access-token"

    def get_authorize_url(self) -> str:
        return "https://example.com/oauth/authorize?stub=1"

    def get_access_token(self, code: str) -> str:
        if code == "bad-code":
            raise ValueError("授权码已失效")
        return self.access_token

    def get_user_info(self, access_token: str) -> OAuthUserInfo:
        return OAuthUserInfo(
            provider=self.name,
            openid=OPENID,
            name=LOGIN,
            email=EMAIL,
            raw_info={"id": int(OPENID), "login": LOGIN},
        )


@pytest.fixture(autouse=True)
def no_debug():
    """debug 模式下全局异常会 re-raise，用例需要的是 JSON 响应。"""
    original_debug = app.debug
    app.debug = False
    yield
    app.debug = original_debug


@pytest.fixture(autouse=True)
def clean_oauth_data(app_context):
    """清理接口用例写入的帐号与授权记录。"""

    def purge():
        with db.auto_commit():
            db.session.execute(
                delete(AccountOAuth).where(AccountOAuth.openid == OPENID)
            )
            db.session.execute(delete(Account).where(Account.email == EMAIL))

    purge()
    yield
    purge()


@pytest.fixture(autouse=True)
def stub_provider():
    """把容器里的提供商注册表换成桩实现。"""
    manager = inject.instance(OAuth2Manager)
    original = manager.get_oauth_instance
    manager.get_oauth_instance = lambda name: (
        _StubProvider() if name == PROVIDER_NAME else None
    )
    yield
    manager.get_oauth_instance = original


def test_oauth_providers_returns_integrated_providers(client):
    """提供商列表接口读取真实注册表，用于渲染登录入口。"""
    # 该接口不经过被替换的 get_oauth_instance，因此反映 .env 中真实配置好的提供商
    body = client.get("/oauth/providers").get_json()

    assert body["code"] == HttpCode.SUCCESS.value
    assert "gitee" in [item["name"] for item in body["data"]["providers"]]
    assert body["data"]["providers"][0]["label"]


def test_oauth_authorize_returns_provider_url(client):
    body = client.get(AUTHORIZE_URL).get_json()

    assert body["code"] == HttpCode.SUCCESS.value
    assert body["data"] == {
        "provider": PROVIDER_NAME,
        "authorize_url": "https://example.com/oauth/authorize?stub=1",
    }


def test_oauth_authorize_unknown_provider_is_not_found(client):
    response = client.get("/oauth/notexists/authorize")

    assert response.get_json()["code"] == HttpCode.NOT_FOUND.value


def test_oauth_callback_without_code_is_validate_error(client):
    body = client.get(CALLBACK_URL).get_json()

    assert body["code"] == HttpCode.VALIDATE_ERROR.value
    assert body["message"]


def test_oauth_callback_with_bad_code_is_fail(client):
    body = client.get(f"{CALLBACK_URL}?code=bad-code").get_json()

    assert body["code"] == HttpCode.FAIL.value
    assert "授权码已失效" in body["message"]


def test_oauth_callback_creates_account_and_returns_token(client):
    first = client.get(f"{CALLBACK_URL}?code=code-1")
    body = first.get_json()

    assert first.status_code == 200
    assert body["code"] == HttpCode.SUCCESS.value
    data = body["data"]
    assert data["token"]
    assert data["oauth_access_token"] == "api-access-token"
    assert data["is_new_account"] is True
    # 首次第三方登录没有密码，前端据此展示初始化密码入口
    assert data["has_password"] is False
    assert data["account"] == {"id": data["account"]["id"], "name": LOGIN, "email": EMAIL}
    assert get_account_id_from_token(
        data["token"], app.config["JWT_SECRET_KEY"]
    ) == str(data["account"]["id"])

    with app.app_context():
        db.session.expire_all()
        assert db.session.query(Account).filter(Account.email == EMAIL).count() == 1
        oauth = (
            db.session.query(AccountOAuth)
            .filter(AccountOAuth.openid == OPENID)
            .one()
        )
        assert str(oauth.account_id) == data["account"]["id"]

    # 第二次登录复用同一个帐号，不重复建号
    second = client.get(f"{CALLBACK_URL}?code=code-2").get_json()
    assert second["data"]["is_new_account"] is False
    assert second["data"]["account"]["id"] == data["account"]["id"]

    with app.app_context():
        db.session.expire_all()
        assert db.session.query(Account).filter(Account.email == EMAIL).count() == 1
        assert db.session.query(AccountOAuth).filter(
            AccountOAuth.openid == OPENID
        ).count() == 1


def test_oauth_callback_persists_login_ip(client):
    body = client.get(f"{CALLBACK_URL}?code=code-1").get_json()

    with app.app_context():
        db.session.expire_all()
        account = db.session.query(Account).filter(Account.email == EMAIL).one()

    assert body["code"] == HttpCode.SUCCESS.value
    assert account.last_login_ip == "127.0.0.1"
    assert account.last_login_at is not None


@pytest.mark.parametrize("path", ["/oauth/providers", AUTHORIZE_URL, CALLBACK_URL])
def test_oauth_endpoints_only_accept_get(client, path):
    """POST 会被全局异常处理转成 fail 响应，这里断言方法受限。"""
    body = client.post(path).get_json()

    assert body["code"] == HttpCode.FAIL.value
    assert "405" in body["message"]
