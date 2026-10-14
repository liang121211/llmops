import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID

from pkg.sqlalchemy import db


class Document(db.Model):
    """知识库文档，关联上传文件与处理规则。"""

    __tablename__ = "document"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_document_id"),
        Index("idx_document_dataset_id", "dataset_id"),
        Index("idx_document_upload_file_id", "upload_file_id"),
    )

    id = Column(UUID, default=uuid.uuid4, nullable=False)
    account_id = Column(UUID, nullable=False)
    dataset_id = Column(UUID, nullable=False)
    upload_file_id = Column(UUID, nullable=False)
    process_rule_id = Column(UUID, nullable=False)
    batch = Column(String(255), default="", nullable=False)
    name = Column(String(255), default="", nullable=False)
    position = Column(Integer, default=0, nullable=False)
    character_count = Column(BigInteger, default=0, nullable=False)
    token_count = Column(BigInteger, default=0, nullable=False)
    processing_started_at = Column(DateTime, nullable=True)
    parsing_completed_at = Column(DateTime, nullable=True)
    splitting_completed_at = Column(DateTime, nullable=True)
    indexing_completed_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    stopped_at = Column(DateTime, nullable=True)
    error = Column(Text, default="", nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    disabled_at = Column(DateTime, nullable=True)
    status = Column(String(255), default="", nullable=False)
    updated_at = Column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )
    created_at = Column(DateTime, default=datetime.now, nullable=False)


__all__ = ["Document"]
