import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Index, PrimaryKeyConstraint, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from pkg.sqlalchemy import db


class ProcessRule(db.Model):
    """文档处理规则，定义知识库文档的清洗与分段策略。"""

    __tablename__ = "process_rule"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_process_rule_id"),
        Index("idx_process_rule_dataset_id", "dataset_id"),
    )

    id = Column(UUID, default=uuid.uuid4, nullable=False)
    account_id = Column(UUID, nullable=False)
    dataset_id = Column(UUID, nullable=False)
    mode = Column(String(255), default="", nullable=False)
    rule = Column(JSONB, default=dict, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )
    created_at = Column(DateTime, default=datetime.now, nullable=False)


__all__ = ["ProcessRule"]
