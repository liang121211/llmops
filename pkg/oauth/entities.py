from dataclasses import dataclass, field
from typing import Any


@dataclass
class OAuthUserInfo:
    """第三方返回的用户信息，已归一成帐号与授权记录需要的字段。"""

    provider: str = ""
    openid: str = ""
    name: str = ""
    email: str = ""
    # 提供商原始返回，便于排查与后续补充字段
    raw_info: dict[str, Any] = field(default_factory=dict)

    def account_values(self) -> dict[str, Any]:
        """转成 account 表需要的写入字段。"""
        return {"name": self.name, "email": self.email}

    def account_oauth_values(self, account_id: Any) -> dict[str, Any]:
        """转成 account_oauth 表需要的写入字段。"""

        return {
            "account_id": account_id,
            "provider": self.provider,
            "openid": self.openid,
        }


__all__ = ["OAuthUserInfo"]
