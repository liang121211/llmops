from dataclasses import dataclass
from typing import Any, ClassVar

import inject
from langchain_core.tools import BaseTool
from sqlalchemy import delete, or_, select

from internal.core.tools.api_tools import (
    ApiProviderManager,
    OpenAPISchema,
    ToolEntity,
    ToolParam,
)
from internal.exception import FailException
from internal.model import ApiTool, ApiToolProvider
from internal.service.base_service import BaseService
from pkg.paginator import PageModel, Paginator, PaginatorReq


@inject.autoparams()
@dataclass
class ApiToolService(BaseService[ApiToolProvider]):
    """API 工具服务层，提供商的通用读写继承自 BaseService。"""

    model: ClassVar[type[ApiToolProvider]] = ApiToolProvider
    api_provider_manager: ApiProviderManager

    def load_openapi_schema(self, openapi_schema: str) -> OpenAPISchema:
        """解析并校验 openapi 规范字符串，规范不合法时抛出 FailException。"""
        return OpenAPISchema.from_content(openapi_schema)

    def get_provider(self, account_id: Any, name: str) -> ApiToolProvider | None:
        """查询账号下指定名字的 API 工具提供商。"""
        return self.get_first(
            ApiToolProvider.account_id == account_id,
            ApiToolProvider.name == name,
        )

    def get_provider_by_id(
        self, account_id: Any, provider_id: Any
    ) -> ApiToolProvider | None:
        """按主键查询账号下的 API 工具提供商，不属于该账号时返回 None。"""
        return self.get_first(
            ApiToolProvider.id == provider_id,
            ApiToolProvider.account_id == account_id,
        )

    def get_tool(
        self, account_id: Any, provider_id: Any, tool_name: str
    ) -> ApiTool | None:
        """查询指定提供商下指定名字的工具，提供商不属于该账号时返回 None。"""
        provider = self.get_provider_by_id(account_id, provider_id)
        if provider is None:
            return None
        stmt = select(ApiTool).where(
            ApiTool.provider_id == provider.id, ApiTool.name == tool_name
        )
        return self.db.session.execute(stmt).scalars().first()

    def get_tool_instance(
        self, account_id: Any, provider_id: Any, tool_name: str
    ) -> BaseTool | None:
        """把数据库里的工具记录包装成可调用的 BaseTool，找不到时返回 None。"""
        tool = self.get_tool(account_id, provider_id, tool_name)
        if tool is None:
            return None
        # get_tool 已经确认过提供商归属，这里再取一次是为了拿到 server 与请求头
        provider = self.get_provider_by_id(account_id, provider_id)
        return self.api_provider_manager.get_tool(
            self._tool_entity(provider, tool),
            headers=self._provider_headers(provider),
        )

    def delete_provider(self, account_id: Any, provider_id: Any) -> bool:
        """删除提供商及其名下的工具，返回是否真正删除了数据。"""
        provider = self.get_provider_by_id(account_id, provider_id)
        if provider is None:
            return False
        # 没有外键级联，名下的工具要在同一个事务里先删掉
        with self.db.auto_commit():
            self.db.session.execute(
                delete(ApiTool).where(ApiTool.provider_id == provider.id)
            )
            self.db.session.delete(provider)
        return True

    def get_providers_with_page(
        self, account_id: Any, req: PaginatorReq, search_word: str = ""
    ) -> PageModel:
        """分页查询账号下的 API 工具提供商，search_word 按名字或描述模糊匹配。"""
        conditions = [ApiToolProvider.account_id == account_id]
        if search_word:
            keyword = f"%{search_word}%"
            conditions.append(
                or_(
                    ApiToolProvider.name.ilike(keyword),
                    ApiToolProvider.description.ilike(keyword),
                )
            )
        stmt = (
            select(ApiToolProvider)
            .where(*conditions)
            .order_by(ApiToolProvider.created_at.desc(), ApiToolProvider.id.desc())
        )
        return Paginator.paginate(stmt, req)

    def create_openapi_schema(
        self,
        account_id: Any,
        name: str,
        icon: str,
        openapi_schema: str,
        headers: list | None = None,
    ) -> ApiToolProvider:
        """按 openapi 规范创建 API 工具提供商及其名下的工具。"""
        # 1. 先解析校验规范，规范不合法直接抛错，不产生任何数据
        schema = self.load_openapi_schema(openapi_schema)
        # 2. 同一账号下提供商名字必须唯一
        if self.exists(ApiToolProvider.account_id == account_id, ApiToolProvider.name == name):
            raise FailException(f"API工具提供者 {name} 已经存在")

        # 3. 提供商与工具必须落在同一个事务里，所以没有使用基类的单表 create
        with self.db.auto_commit():
            provider = ApiToolProvider(
                account_id=account_id,
                name=name,
                icon=icon,
                # 提供商描述直接沿用规范里的 description
                description=schema.description,
                openapi_schema=dict(schema.openapi_schema),
                header=list(headers or []),
            )
            self.db.session.add(provider)
            # 主键由默认值生成，flush 之后才能拿到 provider.id 关联给工具
            self.db.session.flush()
            self.db.session.add_all(
                [
                    self._build_tool(account_id, provider.id, tool)
                    for tool in schema.tools
                ]
            )
        return provider

    @staticmethod
    def _build_tool(account_id: Any, provider_id: Any, tool: ToolEntity) -> ApiTool:
        """把规范解析出的工具转换成入库数据。"""
        return ApiTool(
            account_id=account_id,
            provider_id=provider_id,
            name=tool.name,
            description=tool.description,
            url=tool.url,
            method=tool.method,
            # 参数按 openapi 规范结构存储，保留 in 字段
            parameters=[param.to_dict() for param in tool.parameters],
        )


    @classmethod
    def _tool_entity(cls, provider: ApiToolProvider, tool: ApiTool) -> ToolEntity:
        """把入库的工具记录还原成实体，url 拼上提供商规范里的 server 前缀。"""
        server = str((provider.openapi_schema or {}).get("server", "")).rstrip("/")
        return ToolEntity(
            name=tool.name,
            description=tool.description,
            url=f"{server}{tool.url}",
            method=tool.method,
            parameters=[cls._tool_param(item) for item in (tool.parameters or [])],
        )

    @staticmethod
    def _tool_param(item: dict) -> ToolParam:
        """把入库的一条参数记录还原成参数实体，in 对应实体的 location。"""
        return ToolParam(
            name=item.get("name", ""),
            location=item.get("in", ""),
            description=item.get("description", ""),
            required=bool(item.get("required", False)),
            type=item.get("type", ""),
        )

    @staticmethod
    def _provider_headers(provider: ApiToolProvider) -> dict:
        """提供商上配置的请求头，形如 [{"key": "Authorization", "value": "token"}]。"""
        return {item["key"]: item["value"] for item in (provider.header or [])}


__all__ = ["ApiToolService"]
