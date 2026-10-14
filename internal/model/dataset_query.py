import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Index, PrimaryKeyConstraint, String, Text
from sqlalchemy.dialects.postgresql import UUID

from pkg.sqlalchemy import db


class DatasetQuery(db.Model):
    """知识库查询记录，保存对知识库的检索请求。"""

    __tablename__ = "dataset_query"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_dataset_query_id"),
        Index("idx_dataset_query_dataset_id", "dataset_id"),
    )

    id = Column(UUID, default=uuid.uuid4, nullable=False)
    dataset_id = Column(UUID, nullable=False)
    query = Column(Text, default="", nullable=False)
    source = Column(String(255), default="", nullable=False)
    source_app_id = Column(UUID, nullable=True)
    created_by = Column(UUID, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )
    created_at = Column(DateTime, default=datetime.now, nullable=False)


__all__ = ["DatasetQuery"]
