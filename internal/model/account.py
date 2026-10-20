import uuid
from datetime import datetime

from flask_login import UserMixin
from sqlalchemy import Column, DateTime, Index, PrimaryKeyConstraint, String
from sqlalchemy.dialects.postgresql import UUID

from pkg.sqlalchemy import db


class Account(UserMixin, db.Model):
    """登录账号。密码为空时表示还没设置本地密码。"""

    __tablename__ = "account"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_account_id"),
        Index("idx_account_email", "email"),
    )

    id = Column(UUID, default=uuid.uuid4, nullable=False)
    name = Column(String(255), default="", nullable=False)
    email = Column(String(255), default="", nullable=False)
    # 第三方登录可以不设置本地密码
    password = Column(String(255), default="", nullable=True)
    password_salt = Column(String(255), default="", nullable=True)
    # 账号对应的辅助会话，外键在业务层解决
    assistant_agent_conversation_id = Column(UUID, nullable=True)
    last_login_at = Column(DateTime, default=datetime.now, nullable=False)
    last_login_ip = Column(String(255), default="", nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    def get_id(self) -> str:
        """Flask-Login 要求用户标识是字符串。"""
        return str(self.id)


class AccountOAuth(db.Model):
    """账号绑定的第三方授权。"""

    __tablename__ = "account_oauth"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_account_oauth_id"),
        Index("idx_account_oauth_account_id", "account_id"),
        Index("idx_account_oauth_provider", "provider"),
        Index("idx_account_oauth_openid", "openid"),
    )

    id = Column(UUID, default=uuid.uuid4, nullable=False)
    # 关联账号 id，外键在业务层解决
    account_id = Column(UUID, nullable=False)
    provider = Column(String(255), default="", nullable=False)
    openid = Column(String(255), default="", nullable=False)
    encrypted_token = Column(String(255), default="", nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
