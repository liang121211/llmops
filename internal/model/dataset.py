import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Index, PrimaryKeyConstraint, String, Text, func, select
from sqlalchemy.dialects.postgresql import UUID

from pkg.sqlalchemy import db


class Dataset(db.Model):
    """知识库模型，存储文档集合的基础信息。"""

    __tablename__ = "dataset"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_dataset_id"),
        Index("idx_dataset_account_id", "account_id"),
    )

    id = Column(UUID, default=uuid.uuid4, nullable=False)
    account_id = Column(UUID, nullable=False)
    name = Column(String(255), default="", nullable=False)
    icon = Column(String(255), default="", nullable=False)
    description = Column(Text, default="", nullable=False)
    updated_at = Column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    @property
    def related_app_count(self) -> int:
        """关联的 APP 数量。"""
        from internal.model.app_dataset_join import AppDatasetJoin

        stmt = select(func.count()).where(AppDatasetJoin.dataset_id == self.id)
        return db.session.execute(stmt).scalar() or 0

    @property
    def document_count(self) -> int:
        """知识库关联的文档数量。"""
        from internal.model.document import Document

        stmt = select(func.count()).where(Document.dataset_id == self.id)
        return db.session.execute(stmt).scalar() or 0

    @property
    def character_count(self) -> int:
        """关联文档的总字符数。"""
        from internal.model.document import Document

        stmt = select(func.coalesce(func.sum(Document.character_count), 0)).where(
            Document.dataset_id == self.id
        )
        return db.session.execute(stmt).scalar() or 0


__all__ = ["Dataset"]
