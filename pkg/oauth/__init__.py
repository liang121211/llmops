from pkg.oauth.entities import OAuthUserInfo
from pkg.oauth.gitee_oauth2 import GiteeOAuth2Provider
from pkg.oauth.jwt import generate_token, get_account_id_from_token, parse_token
from pkg.oauth.manager import OAUTH2_PROVIDERS, OAuth2Manager
from pkg.oauth.oauth2 import DEFAULT_EMAIL_SUFFIX, OAuth2Provider

__all__ = [
    "DEFAULT_EMAIL_SUFFIX",
    "GiteeOAuth2Provider",
    "OAUTH2_PROVIDERS",
    "OAuth2Manager",
    "OAuth2Provider",
    "OAuthUserInfo",
    "generate_token",
    "get_account_id_from_token",
    "parse_token",
]
