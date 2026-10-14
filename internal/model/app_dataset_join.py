import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Index, PrimaryKeyConstraint
from sqlalchemy.dialects.postgresql import UUID

from pkg.sqlalchemy import db


class AppDatasetJoin(db.Model):
    """应用与知识库的关联表。"""

    __tablename__ = "app_dataset_join"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_app_dataset_join_id"),
        Index("idx_app_dataset_join_app_id", "app_id"),
        Index("idx_app_dataset_join_dataset_id", "dataset_id"),
    )

    id = Column(UUID, default=uuid.uuid4, nullable=False)
    app_id = Column(UUID, nullable=False)
    dataset_id = Column(UUID, nullable=False)
    created_at = Column(DateTime, default=datetime.now, nullable=False)


__all__ = ["AppDatasetJoin"]
