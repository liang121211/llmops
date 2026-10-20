from pkg.oauth.entities import OAuthUserInfo
from pkg.oauth.oauth2 import OAuth2Provider


class GiteeOAuth2Provider(OAuth2Provider):
    """Gitee 开放平台的 OAuth2 登录实现。

    Gitee 的用户资料接口不一定带邮箱，需要再查一次邮箱列表接口，
    所以这里覆盖 get_user_info，其余流程沿用基类。
    """

    name = "gitee"
    label = "Gitee"
    description = "使用 Gitee 开放平台的 OAuth2 授权登录。"

    def get_user_info(self, access_token: str) -> OAuthUserInfo:
        """读取 Gitee 用户资料，并补齐一个可用于登录的邮箱。"""
        raw_info = self._request(
            "GET", self.user_info_url, params={"access_token": access_token}
        )
        if not isinstance(raw_info, dict):
            raise ValueError(f"OAuth2 提供商 {self.name} 的用户信息格式不正确")
        openid = str(raw_info.get("id", ""))
        return OAuthUserInfo(
            provider=self.name,
            openid=openid,
            name=str(raw_info.get("name") or raw_info.get("login") or openid),
            email=self._pick_email(access_token, raw_info),
            raw_info=raw_info,
        )

    def _pick_email(self, access_token: str, raw_info: dict) -> str:
        """优先取资料里的邮箱，其次取邮箱列表里公开且已验证的，都没有则用占位邮箱。"""
        email = str(raw_info.get("email") or "")
        if email:
            return email
        openid = str(raw_info.get("id", ""))
        if not self.email_info_url:
            return self.default_email(openid, raw_info)
        payload = self._request(
            "GET", self.email_info_url, params={"access_token": access_token}
        )
        emails = payload if isinstance(payload, list) else []
        verified = [
            str(item.get("email") or "")
            for item in emails
            if isinstance(item, dict)
            and item.get("public")
            and item.get("status") == "verified"
        ]
        # 未验证或非公开的邮箱不能当作登录身份，直接回落占位邮箱
        return (verified or [""])[0] or self.default_email(openid, raw_info)


__all__ = ["GiteeOAuth2Provider"]
