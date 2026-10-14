import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Index, PrimaryKeyConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from pkg.sqlalchemy import db


class KeywordTable(db.Model):
    """关键字表，存储知识库的关键词索引数据。"""

    __tablename__ = "keyword_table"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_keyword_table_id"),
        Index("idx_keyword_table_dataset_id", "dataset_id"),
    )

    id = Column(UUID, default=uuid.uuid4, nullable=False)
    dataset_id = Column(UUID, nullable=False)
    keyword_table = Column(JSONB, default=dict, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )
    created_at = Column(DateTime, default=datetime.now, nullable=False)


__all__ = ["KeywordTable"]
