import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Index,
    PrimaryKeyConstraint,
    String,
)
from sqlalchemy.dialects.postgresql import UUID

from pkg.sqlalchemy import db


class UploadFile(db.Model):
    """上传文件模型，保存对象存储中文件的基础信息。"""

    __tablename__ = "upload_file"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_upload_file_id"),
        # 文件都归属到账号，按 account_id 检索
        Index("idx_upload_file_account_id", "account_id"),
    )

    id = Column(UUID, default=uuid.uuid4, nullable=False)
    account_id = Column(UUID, nullable=False)
    name = Column(String(255), default="", nullable=False)  # 文件原始名字
    key = Column(String(255), default="", nullable=False)  # 对象存储里的文件路径
    size = Column(BigInteger, default=0, nullable=False)  # 文件大小，单位字节
    extension = Column(String(255), default="", nullable=False)  # 文件扩展名
    mime_type = Column(String(255), default="", nullable=False)  # 文件媒体类型
    hash = Column(String(255), default="", nullable=False)  # 文件内容的 hash 值
    updated_at = Column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )
    created_at = Column(DateTime, default=datetime.now, nullable=False)


__all__ = ["UploadFile"]
