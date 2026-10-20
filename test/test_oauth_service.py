import inject
import pytest
from sqlalchemy import delete

from config import Config
from internal.exception import FailException, NoFoundException, UnauthorizedException
from internal.model import Account, AccountOAuth
from internal.service import AccountService
from internal.service.oauth_service import OAuthService
from pkg.oauth import DEFAULT_EMAIL_SUFFIX, OAuth2Manager, OAuth2Provider, OAuthUserInfo
from pkg.oauth import get_account_id_from_token
from pkg.sqlalchemy import db

# 桩提供商的名字与返回的用户信息
PROVIDER_NAME = "unit-oauth"
OPENID = "90001"
LOGIN = "demo-user"
# 第三方拿不到邮箱时按规则构造出来的占位邮箱
EMAIL = f"{OPENID}{LOGIN}{DEFAULT_EMAIL_SUFFIX}"


class _StubProvider(OAuth2Provider):
    """不发网络请求的提供商桩，只验证服务层的落库与登录逻辑。"""

    name = PROVIDER_NAME
    label = "单元测试"
    description = "测试用提供商。"

    def __init__(self):
        # 跳过基类的 .env 校验，桩实现不需要真实配置
        self.access_token = "stub-access-token"

    def get_authorize_url(self) -> str:
        return "https://example.com/oauth/authorize"

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
def clean_oauth_data(app_context):
    """清理用例写入的帐号与授权记录。"""

    def purge():
        with db.auto_commit():
            db.session.execute(
                delete(AccountOAuth).where(AccountOAuth.provider == PROVIDER_NAME)
            )
            db.session.execute(delete(Account).where(Account.email == EMAIL))

    purge()
    yield
    purge()


@pytest.fixture
def service():
    return OAuthService(
        manager=OAuth2Manager(providers=(_StubProvider,)),
        account_service=AccountService(db=db, config=inject.instance(Config)),
    )


def _account_count():
    db.session.expire_all()
    return db.session.query(Account).filter(Account.email == EMAIL).count()


def _oauth_rows():
    db.session.expire_all()
    return (
        db.session.query(AccountOAuth)
        .filter(AccountOAuth.provider == PROVIDER_NAME)
        .all()
    )


class TestOAuthProviderLookup:
    """提供商实例与授权参数。"""

    def test_get_providers_and_instance(self, service):
        assert [item.name for item in service.get_providers()] == [PROVIDER_NAME]
        assert service.get_oauth(PROVIDER_NAME).label == "单元测试"
        assert service.get_authorize_url(PROVIDER_NAME) == (
            "https://example.com/oauth/authorize"
        )

    def test_unknown_provider_raises_not_found(self, service):
        with pytest.raises(NoFoundException):
            service.get_oauth("github")
        with pytest.raises(NoFoundException):
            service.login("github", "any-code")

    def test_get_access_token_and_user_info(self, service):
        access_token = service.get_access_token(PROVIDER_NAME, "code-1")
        info = service.get_user_info(PROVIDER_NAME, access_token)

        assert access_token == "stub-access-token"
        assert (info.provider, info.openid, info.email) == (PROVIDER_NAME, OPENID, EMAIL)
        # 实体已经带有数据表需要的字段映射
        assert info.account_values() == {"name": LOGIN, "email": EMAIL}
        assert info.account_oauth_values("account-id") == {
            "account_id": "account-id",
            "provider": PROVIDER_NAME,
            "openid": OPENID,
        }

    def test_token_exchange_failure_becomes_fail_exception(self, service):
        with pytest.raises(FailException):
            service.login(PROVIDER_NAME, "bad-code")


class TestOAuthLogin:
    """第三方登录的建号、复用与密码初始化。"""

    def test_first_login_creates_account_and_oauth(self, service):
        result = service.login(PROVIDER_NAME, "code-1", ip="10.0.0.1")

        assert result.is_new_account is True
        assert result.has_password is False
        assert result.account.password == ""
        assert result.account.last_login_ip == "10.0.0.1"
        assert get_account_id_from_token(
            result.token, inject.instance(Config).JWT_SECRET_KEY
        ) == str(result.account.id)

        rows = _oauth_rows()
        assert len(rows) == 1
        assert rows[0].openid == OPENID
        assert rows[0].account_id == result.account.id
        assert rows[0].encrypted_token == "stub-access-token"

    def test_second_login_reuses_account(self, service):
        first = service.login(PROVIDER_NAME, "code-1")
        second = service.login(PROVIDER_NAME, "code-2")

        assert second.is_new_account is False
        assert second.account.id == first.account.id
        assert _account_count() == 1
        # 同一个授权记录只留一行，令牌刷新成最近一次换取的值
        assert len(_oauth_rows()) == 1
        assert _oauth_rows()[0].encrypted_token == "stub-access-token"

    def test_login_reuses_account_with_same_email(self, service):
        existing = service.account_service.create_account(
            email=EMAIL, name="平台已有帐号", password="123456"
        )

        result = service.login(PROVIDER_NAME, "code-1")

        assert result.account.id == existing.id
        assert result.has_password is True
        assert _account_count() == 1

    def test_oauth_only_account_cannot_use_password_login(self, service):
        result = service.login(PROVIDER_NAME, "code-1")

        # 首次第三方登录没有初始化密码，只能继续走第三方
        with pytest.raises(UnauthorizedException):
            service.account_service.login(EMAIL, "")

    def test_password_works_after_initialization(self, service):
        result = service.login(PROVIDER_NAME, "code-1")

        service.account_service.update_account_password(result.account, "123456")
        account, _ = service.account_service.login(EMAIL, "123456")

        assert account.id == result.account.id
