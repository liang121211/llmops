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
from sqlalchemy.dialects.postgresql import JSONB, UUID

from pkg.sqlalchemy import db


class Segment(db.Model):
    """文档片段，知识库检索的最小单元。"""

    __tablename__ = "segment"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_segment_id"),
        Index("idx_segment_dataset_id", "dataset_id"),
        Index("idx_segment_document_id", "document_id"),
    )

    id = Column(UUID, default=uuid.uuid4, nullable=False)
    account_id = Column(UUID, nullable=False)
    dataset_id = Column(UUID, nullable=False)
    document_id = Column(UUID, nullable=False)
    node_id = Column(String(255), default="", nullable=False)
    position = Column(Integer, default=0, nullable=False)
    content = Column(Text, default="", nullable=False)
    character_count = Column(Integer, default=0, nullable=False)
    token_count = Column(Integer, default=0, nullable=False)
    keywords = Column(JSONB, default=list, nullable=False)
    hash = Column(String(255), default="", nullable=False)
    hit_count = Column(BigInteger, default=0, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    disabled_at = Column(DateTime, nullable=True)
    processing_started_at = Column(DateTime, nullable=True)
    indexing_completed_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    stopped_at = Column(DateTime, nullable=True)
    error = Column(Text, default="", nullable=False)
    status = Column(String(255), default="", nullable=False)
    updated_at = Column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )
    created_at = Column(DateTime, default=datetime.now, nullable=False)


__all__ = ["Segment"]
