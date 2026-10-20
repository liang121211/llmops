import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, Index, Integer, PrimaryKeyConstraint, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from pkg.sqlalchemy import db


class Conversation(db.Model):
    """会话。一次应用对话的主题、摘要和置顶状态。"""

    __tablename__ = "conversation"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_conversation_id"),
        Index("idx_conversation_app_id", "app_id"),
        Index("idx_conversation_created_by", "created_by"),
    )

    id = Column(UUID, default=uuid.uuid4, nullable=False)
    # 应用 id，外键在业务层解决
    app_id = Column(UUID, nullable=False)
    name = Column(String(255), default="", nullable=False)
    summary = Column(Text, default="", nullable=False)
    is_pinned = Column(Boolean, default=False, nullable=False)
    is_delete = Column(Boolean, default=False, nullable=False)
    # 会话来源，例如调试或正式调用
    invoke_from = Column(String(255), default="", nullable=False)
    created_by = Column(UUID, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    created_at = Column(DateTime, default=datetime.now, nullable=False)


class Message(db.Model):
    """一条用户问题和对应的 AI 回答。"""

    __tablename__ = "message"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_message_id"),
        Index("idx_message_app_id", "app_id"),
        Index("idx_message_conversation_id", "conversation_id"),
        Index("idx_message_created_by", "created_by"),
    )

    id = Column(UUID, default=uuid.uuid4, nullable=False)
    app_id = Column(UUID, nullable=False)
    conversation_id = Column(UUID, nullable=False)
    invoke_from = Column(String(255), default="", nullable=False)
    created_by = Column(UUID, nullable=False)
    query = Column(Text, default="", nullable=False)
    # 最终交给模型的消息列表
    message = Column(JSONB, default=dict, nullable=False)
    message_token_count = Column(Integer, default=0, nullable=False)
    message_unit_price = Column(Float, default=0, nullable=False)
    message_price_unit = Column(Float, default=0, nullable=False)
    answer = Column(Text, default="", nullable=False)
    answer_token_count = Column(Integer, default=0, nullable=False)
    answer_unit_price = Column(Float, default=0, nullable=False)
    answer_price_unit = Column(Float, default=0, nullable=False)
    latency = Column(Float, default=0, nullable=False)
    total_token_count = Column(Integer, default=0, nullable=False)
    total_price = Column(Float, default=0, nullable=False)
    status = Column(String(255), default="", nullable=False)
    error = Column(Text, default="", nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    created_at = Column(DateTime, default=datetime.now, nullable=False)


class MessageAgentThought(db.Model):
    """一条消息里的推理步骤，记录思考、工具调用和观察结果。"""

    __tablename__ = "message_agent_thought"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_message_agent_thought_id"),
        Index("idx_message_agent_thought_app_id", "app_id"),
        Index("idx_message_agent_thought_conversation_id", "conversation_id"),
        Index("idx_message_agent_thought_message_id", "message_id"),
        Index("idx_message_agent_thought_created_by", "created_by"),
    )

    id = Column(UUID, default=uuid.uuid4, nullable=False)
    app_id = Column(UUID, nullable=False)
    conversation_id = Column(UUID, nullable=False)
    message_id = Column(UUID, nullable=False)
    invoke_from = Column(String(255), default="", nullable=False)
    created_by = Column(UUID, nullable=False)
    position = Column(Integer, default=0, nullable=False)
    event = Column(String(255), default="", nullable=False)
    thought = Column(Text, default="", nullable=False)
    observation = Column(Text, default="", nullable=False)
    tool = Column(Text, default="", nullable=False)
    tool_label = Column(Text, default="", nullable=False)
    tool_params = Column(JSONB, default=dict, nullable=False)
    tool_input = Column(JSONB, default=dict, nullable=False)
    # 这一步推理用到的消息列表
    message = Column(JSONB, default=list, nullable=False)
    message_token_count = Column(Integer, default=0, nullable=False)
    message_unit_price = Column(Float, default=0, nullable=False)
    message_price_unit = Column(Float, default=0, nullable=False)
    answer = Column(Text, default="", nullable=False)
    answer_token_count = Column(Integer, default=0, nullable=False)
    answer_unit_price = Column(Float, default=0, nullable=False)
    answer_price_unit = Column(Float, default=0, nullable=False)
    total_token_count = Column(Integer, default=0, nullable=False)
    total_price = Column(Float, default=0, nullable=False)
    latency = Column(Float, default=0, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
