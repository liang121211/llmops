import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    PrimaryKeyConstraint,
    String,
    Text,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from pkg.sqlalchemy import db


class ApiToolProvider(db.Model):
    """API 工具提供商模型，保存第三方 API 的 OpenAPI 规范与请求头配置。"""

    __tablename__ = "api_tool_provider"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_api_tool_provider_id"),
        # 账号下按提供商名字检索，建 account_id + name 联合索引
        Index("idx_api_tool_provider_account_id_name", "account_id", "name"),
    )

    id = Column(UUID, default=uuid.uuid4, nullable=False)
    account_id = Column(UUID, nullable=False)
    name = Column(String(255), default="", nullable=False)  # 提供者名字
    icon = Column(String(255), default="", nullable=False)  # 提供者图标地址
    description = Column(Text, default="", nullable=False)  # 提供者描述
    # 接口完整的 OpenAPI 规范，用字典存储便于业务层解析出工具列表
    openapi_schema = Column(JSONB, default=dict, nullable=False)
    # 调用接口所需的请求头，形如 [{"key": "Authorization", "value": "token"}]
    header = Column(JSONB, default=list, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.now, onupdate=datetime.now, nullable=False
    )
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    @property
    def tools(self) -> list["ApiTool"]:
        """提供商名下的全部 API 工具；外键在业务层解决，这里按 provider_id 现查。"""
        # 延迟导入，避免与 api_tool 模块相互引用
        from internal.model.api_tool import ApiTool

        stmt = select(ApiTool).where(ApiTool.provider_id == self.id)
        return list(db.session.execute(stmt).scalars().all())


__all__ = ["ApiToolProvider"]
