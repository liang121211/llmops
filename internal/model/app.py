import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Index, PrimaryKeyConstraint, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from pkg.sqlalchemy import db


class App(db.Model):
    """AI应用模型"""

    __tablename__ = "app"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_app_id"),
        Index("idx_app_account_id", "account_id"),
    )

    id = Column(UUID, default=uuid.uuid4, nullable=False)
    account_id = Column(UUID, nullable=False)
    name = Column(String(255), default="", nullable=False)
    icon = Column(String(255), default="", nullable=False)
    config = Column(JSONB, default={}, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )
    created_at = Column(DateTime, default=datetime.now, nullable=False)


__all__ = ["App"]
