import os
from urllib.parse import urlencode

import requests

from pkg.oauth.entities import OAuthUserInfo

# 第三方没有返回可用邮箱时使用的占位邮箱后缀
DEFAULT_EMAIL_SUFFIX = "@user.no-replay@brtc.com"
# 各提供商参数按 OAUTH2_<大写提供商名>_<字段> 约定放在 .env 里
CONFIG_PREFIX = "OAUTH2_"
# 授权码模式的固定参数
GRANT_TYPE = "authorization_code"
# 请求第三方的超时时间（秒）
REQUEST_TIMEOUT = 15


class OAuth2Provider:
    """OAuth2 授权码登录的通用实现。

    新增一个提供商只需要继承本类、声明 name/label/description，
    再在 .env 里补齐 OAUTH2_<大写名称>_ 前缀的参数即可；
    字段含义与第三方不一致时，覆盖 to_user_info 或 get_user_info。
    """

    name = ""
    label = ""
    description = ""
    # 授权时申请的资源范围，多数平台用 user_info 读取基本资料
    scope = "user_info"

    def __init__(self):
        prefix = f"{CONFIG_PREFIX}{self.name.upper()}_"
        self.client_id = os.environ.get(f"{prefix}CLIENT_ID", "")
        self.client_secret = os.environ.get(f"{prefix}CLIENT_SECRET", "")
        self.redirect_uri = os.environ.get(f"{prefix}REDIRECT_URI", "")
        self.auth_url = os.environ.get(f"{prefix}AUTH_URL", "")
        self.token_url = os.environ.get(f"{prefix}TOKEN_URL", "")
        self.user_info_url = os.environ.get(f"{prefix}USER_INFO_URL", "")
        self.email_info_url = os.environ.get(f"{prefix}EMAIL_INFO_URL", "")
        required = (self.client_id, self.client_secret, self.auth_url, self.token_url)
        if self.name == "" or not all(required) or not self.user_info_url:
            raise ValueError(f"OAuth2 提供商 {self.name or '未命名'} 的 .env 配置不完整")

    def get_authorize_url(self) -> str:
        """拼出第三方授权页地址，用户同意后会带 code 回到 redirect_uri。"""
        query = urlencode(
            {
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "response_type": "code",
                "scope": self.scope,
            }
        )
        return f"{self.auth_url}?{query}"

    def get_access_token(self, code: str) -> str:
        """用授权码换取访问令牌 access_token。"""
        payload = self._request(
            "POST",
            self.token_url,
            data={
                "grant_type": GRANT_TYPE,
                "code": code,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": self.redirect_uri,
            },
        )
        access_token = payload.get("access_token") if isinstance(payload, dict) else None
        if not access_token:
            raise ValueError(f"OAuth2 提供商 {self.name} 没有返回 access_token")
        return str(access_token)

    def get_user_info(self, access_token: str) -> OAuthUserInfo:
        """读取用户资料并归一成数据表需要的字段。"""
        raw_info = self._request(
            "GET", self.user_info_url, params={"access_token": access_token}
        )
        if not isinstance(raw_info, dict):
            raise ValueError(f"OAuth2 提供商 {self.name} 的用户信息格式不正确")
        return self.to_user_info(raw_info)

    def to_user_info(self, raw_info: dict) -> OAuthUserInfo:
        """把第三方原始返回转成 OAuthUserInfo，字段名不同则覆盖本方法。"""
        openid = str(raw_info.get("id", ""))
        name = str(raw_info.get("name") or raw_info.get("login") or openid)
        email = str(raw_info.get("email") or "") or self.default_email(openid, raw_info)
        return OAuthUserInfo(
            provider=self.name,
            openid=openid,
            name=name,
            email=email,
            raw_info=raw_info,
        )

    def default_email(self, openid: str, raw_info: dict) -> str:
        """第三方拿不到邮箱时，用 openid + login + 固定后缀构造占位邮箱。"""
        login = str(raw_info.get("login") or "")
        return f"{openid}{login}{DEFAULT_EMAIL_SUFFIX}"

    def _request(
        self,
        method: str,
        url: str,
        params: dict | None = None,
        data: dict | None = None,
    ):
        """统一发起请求并解析 JSON，非 2xx 时抛出带提供商名字的异常。

        返回值保持第三方给到的结构（多数接口是字典，邮箱一类的接口是列表）。
        """
        response = requests.request(
            method,
            url,
            params=params,
            data=data,
            headers={"Accept": "application/json"},
            timeout=REQUEST_TIMEOUT,
        )
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if response.status_code >= 400:
            reason = ""
            if isinstance(payload, dict):
                reason = payload.get("error_description") or ""
            raise ValueError(
                f"OAuth2 提供商 {self.name} 请求失败：{reason or response.text[:200]}"
            )
        return payload


__all__ = [
    "CONFIG_PREFIX",
    "DEFAULT_EMAIL_SUFFIX",
    "GRANT_TYPE",
    "OAuth2Provider",
    "REQUEST_TIMEOUT",
]
