from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

from pkg.oauth import (
    DEFAULT_EMAIL_SUFFIX,
    GiteeOAuth2Provider,
    OAuth2Manager,
    OAuth2Provider,
)
from pkg.oauth import oauth2 as oauth2_module

GITEE_ENV = {
    "OAUTH2_GITEE_CLIENT_ID": "test-client-id",
    "OAUTH2_GITEE_CLIENT_SECRET": "test-client-secret",
    "OAUTH2_GITEE_REDIRECT_URI": "http://127.0.0.1:5173/oauth/gitee",
    "OAUTH2_GITEE_AUTH_URL": "https://gitee.com/oauth/authorize",
    "OAUTH2_GITEE_TOKEN_URL": "https://gitee.com/oauth/token",
    "OAUTH2_GITEE_USER_INFO_URL": "https://gitee.com/api/v5/user",
    "OAUTH2_GITEE_EMAIL_INFO_URL": "https://gitee.com/api/v5/emails",
}
TOKEN_URL = GITEE_ENV["OAUTH2_GITEE_TOKEN_URL"]
USER_URL = GITEE_ENV["OAUTH2_GITEE_USER_INFO_URL"]
EMAILS_URL = GITEE_ENV["OAUTH2_GITEE_EMAIL_INFO_URL"]


@pytest.fixture
def gitee(monkeypatch):
    """按测试用的 .env 值构造 Gitee 提供商，不依赖真实密钥。"""
    for key, value in GITEE_ENV.items():
        monkeypatch.setenv(key, value)
    return GiteeOAuth2Provider()


def _patch_requests(monkeypatch, payloads):
    """按调用顺序返回预置的 (状态码, JSON)，并记录每次调用的参数。"""
    calls = []
    queue = list(payloads)

    def fake_request(method, url, params=None, data=None, headers=None, timeout=None):
        calls.append(
            SimpleNamespace(
                method=method, url=url, params=params, data=data, timeout=timeout
            )
        )
        status_code, payload = queue.pop(0)
        return SimpleNamespace(
            status_code=status_code,
            json=lambda: payload,
            text=str(payload),
        )

    monkeypatch.setattr(oauth2_module, "requests", SimpleNamespace(request=fake_request))
    return calls


class TestAuthorizeAndToken:
    """授权地址拼接与授权码换令牌。"""

    def test_authorize_url_carries_required_query(self, gitee):
        query = parse_qs(urlparse(gitee.get_authorize_url()).query)

        assert urlparse(gitee.get_authorize_url()).scheme == "https"
        assert query["client_id"] == ["test-client-id"]
        assert query["redirect_uri"] == [GITEE_ENV["OAUTH2_GITEE_REDIRECT_URI"]]
        assert query["response_type"] == ["code"]
        assert query["scope"] == ["user_info"]

    def test_access_token_exchange_posts_form_data(self, gitee, monkeypatch):
        calls = _patch_requests(monkeypatch, [(200, {"access_token": "at-1"})])

        assert gitee.get_access_token("code-1") == "at-1"
        assert calls[0].method == "POST"
        assert calls[0].url == TOKEN_URL
        assert calls[0].data == {
            "grant_type": "authorization_code",
            "code": "code-1",
            "client_id": "test-client-id",
            "client_secret": "test-client-secret",
            "redirect_uri": GITEE_ENV["OAUTH2_GITEE_REDIRECT_URI"],
        }
        assert calls[0].timeout == oauth2_module.REQUEST_TIMEOUT

    def test_missing_access_token_raises(self, gitee, monkeypatch):
        _patch_requests(monkeypatch, [(200, {"error": "invalid_request"})])

        with pytest.raises(ValueError, match="没有返回 access_token"):
            gitee.get_access_token("code-1")

    def test_http_error_exposes_reason(self, gitee, monkeypatch):
        _patch_requests(monkeypatch, [(400, {"error_description": "code已使用"})])

        with pytest.raises(ValueError, match="code已使用"):
            gitee.get_access_token("code-1")


class TestUserInfo:
    """用户信息归一与邮箱兜底。"""

    def test_user_info_maps_fields(self, gitee, monkeypatch):
        _patch_requests(
            monkeypatch,
            [(200, {"id": 123, "login": "tom", "name": "Tom", "email": "tom@example.com"})],
        )

        info = gitee.get_user_info("at-1")

        assert info.provider == "gitee"
        assert info.openid == "123"
        assert info.name == "Tom"
        assert info.email == "tom@example.com"
        assert info.raw_info["login"] == "tom"

    def test_user_info_falls_back_to_login_name(self, gitee, monkeypatch):
        _patch_requests(
            monkeypatch,
            [(200, {"id": 123, "login": "tom", "name": ""}), (200, [])],
        )

        assert gitee.get_user_info("at-1").name == "tom"

    def test_non_dict_user_info_raises(self, gitee, monkeypatch):
        _patch_requests(monkeypatch, [(200, ["unexpected"])])

        with pytest.raises(ValueError, match="用户信息格式不正确"):
            gitee.get_user_info("at-1")

    def test_email_taken_from_emails_list(self, gitee, monkeypatch):
        _patch_requests(
            monkeypatch,
            [
                (200, {"id": 123, "login": "tom", "name": "Tom", "email": ""}),
                (
                    200,
                    [
                        {"email": "private@example.com", "public": False, "status": "verified"},
                        {"email": "public@example.com", "public": True, "status": "verified"},
                    ],
                ),
            ],
        )

        assert gitee.get_user_info("at-1").email == "public@example.com"

    def test_email_falls_back_to_default_box(self, gitee, monkeypatch):
        _patch_requests(
            monkeypatch,
            [
                (200, {"id": 123, "login": "tom", "name": "Tom", "email": ""}),
                (
                    200,
                    [
                        {"email": "private@example.com", "public": False, "status": "verified"},
                        {"email": "unverified@example.com", "public": True, "status": "pending"},
                    ],
                ),
            ],
        )

        # 公开且已验证的都没有时，用 openid+login+固定后缀构造占位邮箱
        assert gitee.get_user_info("at-1").email == f"123tom{DEFAULT_EMAIL_SUFFIX}"

    def test_default_email_without_emails_url(self, gitee, monkeypatch):
        gitee.email_info_url = ""

        assert gitee.default_email("123", {"login": "tom"}) == f"123tom{DEFAULT_EMAIL_SUFFIX}"


class TestProviderExtension:
    """新增提供商只需要继承与配置。"""

    def test_base_provider_requires_configuration(self, monkeypatch):
        # 基类没有名字，也读不到任何 .env 配置
        with pytest.raises(ValueError, match="配置不完整"):
            OAuth2Provider()

    def test_missing_client_secret_is_rejected(self, monkeypatch):
        for key, value in GITEE_ENV.items():
            monkeypatch.setenv(key, value)
        monkeypatch.delenv("OAUTH2_GITEE_CLIENT_SECRET")

        with pytest.raises(ValueError, match="配置不完整"):
            GiteeOAuth2Provider()

    def test_subclass_works_with_only_env_configuration(self, monkeypatch):
        for key, value in {
            "OAUTH2_DEMO_CLIENT_ID": "demo-id",
            "OAUTH2_DEMO_CLIENT_SECRET": "demo-secret",
            "OAUTH2_DEMO_REDIRECT_URI": "http://127.0.0.1:5173/oauth/demo",
            "OAUTH2_DEMO_AUTH_URL": "https://demo.com/oauth/authorize",
            "OAUTH2_DEMO_TOKEN_URL": "https://demo.com/oauth/token",
            "OAUTH2_DEMO_USER_INFO_URL": "https://demo.com/api/user",
        }.items():
            monkeypatch.setenv(key, value)

        class DemoOAuth2Provider(OAuth2Provider):
            name = "demo"
            label = "Demo"
            description = "只靠继承与配置接入的提供商。"

        calls = _patch_requests(monkeypatch, [(200, {"id": 9, "login": "demo"})])
        manager = OAuth2Manager(providers=(DemoOAuth2Provider,))

        provider = manager.get_oauth_instance("demo")
        assert provider is not None
        info = provider.get_user_info("at-9")
        # 基类默认映射：id 作 openid，name 缺失时回落 login
        assert info.openid == "9"
        assert info.name == "demo"
        assert info.email == f"9demo{DEFAULT_EMAIL_SUFFIX}"
        assert calls[0].url == "https://demo.com/api/user"
        assert [item.name for item in manager.get_providers()] == ["demo"]


class TestOAuth2Manager:
    """提供商注册表。"""

    def test_registry_contains_gitee(self, gitee, monkeypatch):
        for key, value in GITEE_ENV.items():
            monkeypatch.setenv(key, value)

        manager = OAuth2Manager()

        assert [item.name for item in manager.get_providers()] == ["gitee"]
        assert manager.get_oauth_instance("gitee").label == "Gitee"
        # Github 暂未实现，不在注册表里
        assert manager.get_oauth_instance("github") is None
