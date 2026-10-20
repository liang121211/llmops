import datetime
import uuid

import jwt as pyjwt
import pytest
from sqlalchemy import delete

from internal.exception import UnauthorizedException, ValidateException
from internal.model import Account, AccountOAuth
from internal.service import AccountService
from pkg.oauth import generate_token, get_account_id_from_token, parse_token
from pkg.password import hash_password
from pkg.sqlalchemy import db

# 用例邮箱统一前缀，方便结束后清理
TEST_EMAIL_PREFIX = "login-test-"
SECRET = "unit-test-secret"


@pytest.fixture(autouse=True)
def clean_accounts(app_context):
    """用例真实写库，前后都按邮箱前缀清掉测试账号。"""

    def purge():
        with db.auto_commit():
            db.session.execute(
                delete(Account).where(Account.email.like(f"{TEST_EMAIL_PREFIX}%"))
            )
            db.session.execute(
                delete(AccountOAuth).where(AccountOAuth.provider == "unit-test")
            )

    purge()
    yield
    purge()


@pytest.fixture
def service():
    return AccountService(db=db, config=_FakeConfig())


class _FakeConfig:
    """只提供账号服务需要的 JWT 配置，避免用例依赖真实 .env。"""

    JWT_SECRET_KEY = SECRET
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRE_DAYS = 30


def _email(name="user"):
    return f"{TEST_EMAIL_PREFIX}{name}@example.com"


class TestJwt:
    """JWT 凭证签发与解析。"""

    def test_token_roundtrip_carries_account_id(self):
        account_id = uuid.uuid4()
        token = generate_token(account_id, SECRET, expire_days=7)

        payload = parse_token(token, SECRET)
        assert payload["data"]["account_id"] == str(account_id)
        assert get_account_id_from_token(token, SECRET) == str(account_id)

    def test_default_expire_is_thirty_days(self):
        token = generate_token(uuid.uuid4(), SECRET)

        payload = parse_token(token, SECRET)
        # exp 与 iat 的差值就是配置的有效期
        assert payload["exp"] - payload["iat"] == 30 * 24 * 3600

    def test_expired_token_is_rejected(self):
        token = generate_token(uuid.uuid4(), SECRET, expire_days=-1)

        with pytest.raises(pyjwt.ExpiredSignatureError):
            parse_token(token, SECRET)
        assert get_account_id_from_token(token, SECRET) is None

    def test_token_with_other_secret_is_rejected(self):
        token = generate_token(uuid.uuid4(), SECRET)

        assert get_account_id_from_token(token, "another-secret") is None


class TestAccountServiceRead:
    """账号与第三方授权记录的读取。"""

    def test_get_account_accepts_string_and_uuid(self, service):
        account = service.create_account(email=_email(), name="读取", password="123456")

        assert service.get_account(account.id) is account
        assert service.get_account(str(account.id)).id == account.id
        assert service.get_account("not-a-uuid") is None

    def test_get_account_by_email(self, service):
        service.create_account(email=_email("by-email"), name="按邮箱")

        found = service.get_account_by_email(_email("by-email"))
        assert found.name == "按邮箱"
        assert service.get_account_by_email(_email("missing")) is None

    def test_get_account_oauth_by_provider_and_openid(self, service):
        account = service.create_account(email=_email("oauth"), name="第三方")
        oauth = AccountOAuth(
            id=uuid.uuid4(),
            account_id=account.id,
            provider="unit-test",
            openid="openid-1",
            encrypted_token="token",
            updated_at=datetime.datetime.now(),
            created_at=datetime.datetime.now(),
        )
        with db.auto_commit():
            db.session.add(oauth)

        found = service.get_account_oauth("unit-test", "openid-1")
        assert found.account_id == account.id
        assert service.get_account_oauth("unit-test", "openid-x") is None


class TestAccountServiceWrite:
    """账号创建与信息更新。"""

    def test_create_account_hashes_password(self, service):
        account = service.create_account(email=_email(), name="哈希", password="123456")

        assert account.password != "123456"
        assert len(account.password) == 64
        assert account.password_salt
        assert hash_password("123456", account.password_salt) == account.password

    def test_create_account_without_password(self, service):
        account = service.create_account(email=_email("oauth-only"), name="仅第三方")

        # 第三方登录的帐号没有本地密码，校验时一律失败
        assert account.password == ""
        assert account.password_salt == ""
        assert service.verify_password(account, "") is False

    def test_create_account_rejects_duplicate_email(self, service):
        service.create_account(email=_email("dup"), name="第一个")

        with pytest.raises(ValidateException):
            service.create_account(email=_email("dup"), name="第二个")

    def test_create_account_requires_email(self, service):
        with pytest.raises(ValidateException):
            service.create_account(name="没有邮箱")

    def test_update_account_changes_fields(self, service):
        account = service.create_account(email=_email(), name="原名", password="123456")

        updated = service.update_account(account, name="新名", email=_email("new"))

        assert updated.name == "新名"
        assert updated.email == _email("new")
        # 没给出 password 时原密码摘要保持不变
        assert service.verify_password(updated, "123456")

    def test_update_account_rehashes_password(self, service):
        account = service.create_account(email=_email(), name="改密码", password="123456")
        old_hash = account.password

        updated = service.update_account(account, password="654321")

        assert updated.password != old_hash
        assert service.verify_password(updated, "654321")

    def test_update_account_rejects_used_email(self, service):
        service.create_account(email=_email("taken"), name="占用者")
        account = service.create_account(email=_email(), name="改名者")

        with pytest.raises(ValidateException):
            service.update_account(account, email=_email("taken"))

    def test_update_account_password_rotates_salt(self, service):
        account = service.create_account(email=_email(), name="轮换", password="123456")
        old_salt = account.password_salt

        updated = service.update_account_password(account, "abcdef")

        assert updated.password_salt != old_salt
        assert service.verify_password(updated, "abcdef")
        assert service.verify_password(updated, "123456") is False

    def test_update_account_password_rejects_empty(self, service):
        account = service.create_account(email=_email(), name="空密码", password="123456")

        with pytest.raises(ValidateException):
            service.update_account_password(account, "")


class TestAccountLogin:
    """邮箱密码登录与 JWT 签发。"""

    def test_login_returns_account_and_token(self, service):
        service.create_account(email=_email(), name="登录", password="123456")

        account, token = service.login(_email(), "123456", ip="127.0.0.1")

        assert account.email == _email()
        assert account.last_login_ip == "127.0.0.1"
        assert get_account_id_from_token(token, SECRET) == str(account.id)

    def test_login_failures_share_one_message(self, service):
        service.create_account(email=_email(), name="存在", password="123456")

        with pytest.raises(UnauthorizedException) as missing:
            service.login(_email("nobody"), "123456")
        with pytest.raises(UnauthorizedException) as wrong:
            service.login(_email(), "000000")
        # 提示一致，避免暴露邮箱是否注册过
        assert missing.value.message == wrong.value.message

    def test_login_rejects_account_without_password(self, service):
        service.create_account(email=_email("oauth-only"), name="仅第三方")

        with pytest.raises(UnauthorizedException):
            service.login(_email("oauth-only"), "")
