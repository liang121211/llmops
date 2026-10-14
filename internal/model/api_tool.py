import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    PrimaryKeyConstraint,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from pkg.sqlalchemy import db


class ApiTool(db.Model):
    """API 工具模型，一条记录对应某个提供商 OpenAPI 规范中的一个接口。"""

    __tablename__ = "api_tool"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_api_tool_id"),
        # 按 id + provider_id + name 定位工具，建联合索引
        Index("idx_api_tool_id_provider_id_name", "id", "provider_id", "name"),
    )

    id = Column(UUID, default=uuid.uuid4, nullable=False)
    account_id = Column(UUID, nullable=False)
    provider_id = Column(UUID, nullable=False)  # 所属提供商 id，外键关系在业务层维护
    name = Column(String(255), default="", nullable=False)  # 工具名字
    description = Column(Text, default="", nullable=False)  # 工具描述
    url = Column(String(512), default="", nullable=False)  # 工具 API 地址
    method = Column(String(16), default="", nullable=False)  # 请求方法
    # 工具参数列表，形如 [{"name": "city", "type": "string", "required": true}]
    parameters = Column(JSONB, default=list, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    @property
    def provider(self) -> "ApiToolProvider | None":
        """工具所属的提供商；外键在业务层解决，这里按 provider_id 现查。"""
        # 延迟导入，避免与 api_tool_provider 模块相互引用
        from internal.model.api_tool_provider import ApiToolProvider

        return db.session.get(ApiToolProvider, self.provider_id)


__all__ = ["ApiTool"]
