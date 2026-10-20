import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, ClassVar

import inject
from sqlalchemy import select

from config import Config
from internal.exception import UnauthorizedException, ValidateException
from internal.model import Account, AccountOAuth
from internal.service.base_service import BaseService
from pkg.oauth import generate_token
from pkg.password import hash_password, verify_password


def to_uuid(value: Any):
    """把字符串主键转成 UUID，非法值返回 None。"""
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


@inject.autoparams()
@dataclass
class AccountService(BaseService[Account]):
    """账号服务层：账号读写、密码哈希校验与邮箱密码登录。"""

    model: ClassVar[type[Account]] = Account

    config: Config

    def get_account(self, account_id: Any) -> Account | None:
        """根据账号 ID 获取帐号信息，ID 不合法时按查无此人处理。"""
        account_uuid = to_uuid(account_id)
        if account_uuid is None:
            return None
        return self.get_by_id(account_uuid)

    def get_account_by_email(self, email: str) -> Account | None:
        """根据 Email 获取指定的帐号信息。"""
        return self.get_first(Account.email == email)

    def get_account_oauth(self, provider: str, openid: str) -> AccountOAuth | None:
        """根据第三方提供商名字与 OpenID 获取授权认证记录。"""
        stmt = (
            select(AccountOAuth)
            .where(AccountOAuth.provider == provider)
            .where(AccountOAuth.openid == openid)
        )
        return self.db.session.execute(stmt).scalars().first()

    def create_account(self, **values: Any) -> Account:
        """按键值对创建帐号，明文密码在这里加盐哈希后才落库。"""
        email = str(values.get("email") or "")
        if not email:
            raise ValidateException("创建帐号必须提供邮箱")
        if self.exists(Account.email == email):
            raise ValidateException(f"帐号 {email} 已经存在")
        password = str(values.pop("password", "") or "")
        # 第三方登录的帐号可以不设置本地密码，此时盐值与密码一起留空
        if password:
            salt = uuid.uuid4().hex
            values["password"] = hash_password(password, salt)
            values["password_salt"] = salt
        else:
            values["password"] = ""
            values["password_salt"] = ""
        return self.create(**values)

    def update_account(self, account: Account, **values: Any) -> Account | None:
        """更新帐号信息，password 传入时重新加盐哈希。"""
        values.pop("id", None)
        email = values.get("email")
        if email and email != account.email and self.exists(Account.email == email):
            raise ValidateException(f"帐号 {email} 已经存在")
        password = values.get("password")
        if password is not None:
            salt = uuid.uuid4().hex
            values["password"] = hash_password(str(password), salt)
            values["password_salt"] = salt
        return self.update(account.id, **values)

    def update_account_password(self, account: Account, password: str) -> Account | None:
        """更新帐号密码，每次写入都换新盐值。"""
        if not password:
            raise ValidateException("密码不能为空")
        salt = uuid.uuid4().hex
        return self.update(
            account.id, password=hash_password(password, salt), password_salt=salt
        )

    def create_account_oauth(self, **values: Any) -> AccountOAuth:
        """新增一条第三方授权记录并提交。"""
        instance = AccountOAuth(**values)
        with self.db.auto_commit():
            self.db.session.add(instance)
        return instance

    def update_account_oauth(
        self, account_oauth: AccountOAuth, **values: Any
    ) -> AccountOAuth:
        """更新第三方授权记录，例如换回新的访问令牌。"""
        with self.db.auto_commit():
            for field, value in values.items():
                if value is None:
                    continue
                setattr(account_oauth, field, value)
        return account_oauth

    def verify_password(self, account: Account, password: str) -> bool:
        """校验明文密码是否匹配帐号的密码摘要。"""
        if not account.password or not account.password_salt:
            return False
        return verify_password(password, account.password_salt, account.password)

    def issue_token(self, account: Account, ip: str = "") -> tuple[Account, str]:
        """为已认证的帐号签发 JWT，并刷新登录时间与来源 IP。

        邮箱密码登录与第三方登录共用这一步，返回 (最新帐号, JWT)。
        """
        token = generate_token(
            account.id,
            str(self.config.JWT_SECRET_KEY),
            expire_days=int(self.config.JWT_EXPIRE_DAYS),
            algorithm=str(self.config.JWT_ALGORITHM),
        )
        updated = self.update(account.id, last_login_at=datetime.now(), last_login_ip=ip)
        return updated, token

    def login(self, email: str, password: str, ip: str = "") -> tuple[Account, str]:
        """邮箱密码登录，成功后刷新登录信息并签发默认 30 天的 JWT 凭证。"""
        account = self.get_account_by_email(email)
        # 帐号不存在与密码错误返回同一句提示，避免探测哪些邮箱注册过
        if account is None or not self.verify_password(account, password):
            raise UnauthorizedException("帐号或密码错误")
        return self.issue_token(account, ip)


__all__ = ["AccountService", "to_uuid"]
