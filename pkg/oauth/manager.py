from pkg.oauth.gitee_oauth2 import GiteeOAuth2Provider
from pkg.oauth.oauth2 import OAuth2Provider

# 已集成的第三方登录提供商，新增登录方式时在这里登记一行即可
OAUTH2_PROVIDERS: tuple[type[OAuth2Provider], ...] = (GiteeOAuth2Provider,)


class OAuth2Manager:
    """OAuth2 提供商注册表：负责列出可用提供商并按名字取出实例。"""

    def __init__(self, providers: tuple[type[OAuth2Provider], ...] = OAUTH2_PROVIDERS):
        self.providers = tuple(providers)

    def get_providers(self) -> list[OAuth2Provider]:
        """获取平台集成的所有第三方授权认证提供商。"""
        return [provider() for provider in self.providers]

    def get_oauth_instance(self, provider_name: str) -> OAuth2Provider | None:
        """根据提供商名字获取对应的 OAuth2 实例对象，未集成时返回 None。"""
        for provider in self.providers:
            if provider.name == provider_name:
                return provider()
        return None


__all__ = ["OAUTH2_PROVIDERS", "OAuth2Manager"]
