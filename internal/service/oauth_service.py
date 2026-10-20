from dataclasses import dataclass

import inject

from internal.exception import FailException, NoFoundException
from internal.model import Account
from internal.service.account_service import AccountService
from pkg.oauth import OAuth2Manager, OAuth2Provider, OAuthUserInfo


@dataclass
class OAuthLogin:
    """第三方登录结果：平台 JWT 与帐号状态，供前端决定是否展示初始化密码入口。"""

    account: Account
    token: str
    oauth_access_token: str
    is_new_account: bool
    has_password: bool


@inject.autoparams()
@dataclass
class OAuthService:
    """第三方 OAuth2 登录服务层：换取用户信息并维护帐号与授权记录。"""

    manager: OAuth2Manager
    account_service: AccountService

    def get_providers(self) -> list[OAuth2Provider]:
        """获取平台集成的所有第三方授权认证提供商。"""
        return self.manager.get_providers()

    def get_oauth(self, provider_name: str) -> OAuth2Provider:
        """根据传递的服务提供商，获取授权的 OAuth2 实例对象。"""
        oauth = self.manager.get_oauth_instance(provider_name)
        if oauth is None:
            raise NoFoundException(f"未集成第三方登录提供商 {provider_name}")
        return oauth

    def get_authorize_url(self, provider_name: str) -> str:
        """取指定提供商的授权页地址，前端把用户跳过去即可开始登录。"""
        return self.get_oauth(provider_name).get_authorize_url()

    def get_access_token(self, provider_name: str, code: str) -> str:
        """按 provider_name + code 完成授权认证，返回 access_token。"""
        return self._exchange_token(self.get_oauth(provider_name), code)

    def get_user_info(self, provider_name: str, access_token: str) -> OAuthUserInfo:
        """按 provider_name + access_token 取用户信息，已转成数据表字段。"""
        return self._fetch_user_info(self.get_oauth(provider_name), access_token)

    def login(self, provider_name: str, code: str, ip: str = "") -> OAuthLogin:
        """完整的第三方登录：换令牌、取资料、建号或复用，最后签发平台 JWT。"""
        oauth = self.get_oauth(provider_name)
        access_token = self._exchange_token(oauth, code)
        user_info = self._fetch_user_info(oauth, access_token)
        account, is_new_account = self._sync_account(user_info, access_token)
        account, token = self.account_service.issue_token(account, ip)
        return OAuthLogin(
            account=account,
            token=token,
            oauth_access_token=access_token,
            is_new_account=is_new_account,
            # 首次第三方登录没有密码时，前端需要给出初始化密码的入口
            has_password=bool(account.password),
        )

    def _exchange_token(self, oauth: OAuth2Provider, code: str) -> str:
        """调用提供商换令牌，把底层异常转成接口层的失败响应。"""
        try:
            return oauth.get_access_token(code)
        except ValueError as error:
            raise FailException(str(error)) from error

    def _fetch_user_info(
        self, oauth: OAuth2Provider, access_token: str
    ) -> OAuthUserInfo:
        """调用提供商读取用户资料。"""
        try:
            return oauth.get_user_info(access_token)
        except ValueError as error:
            raise FailException(str(error)) from error

    def _sync_account(
        self, user_info: OAuthUserInfo, access_token: str
    ) -> tuple[Account, bool]:
        """按授权记录定位帐号，没有则新建，返回 (帐号, 是否首次登录)。"""
        oauth = self.account_service.get_account_oauth(
            user_info.provider, user_info.openid
        )
        if oauth is not None:
            account = self.account_service.get_account(oauth.account_id)
            if account is not None:
                # 每次登录都刷新最近一次换取到的访问令牌
                self.account_service.update_account_oauth(
                    oauth, encrypted_token=access_token
                )
                return account, False
        # 占位邮箱之外的情况：邮箱已有平台帐号时直接复用，避免重复建号
        account = self.account_service.get_account_by_email(user_info.email)
        if account is None:
            account = self.account_service.create_account(**user_info.account_values())
        self.account_service.create_account_oauth(
            **user_info.account_oauth_values(account.id),
            encrypted_token=access_token,
        )
        return account, True


__all__ = ["OAuthLogin", "OAuthService"]
