import logging
import os
from dataclasses import dataclass

import inject
from langchain_core.tools import BaseTool

from internal.core.tools.builtin_tools import BuiltinProviderManager
from internal.core.tools.builtin_tools.categories import (
    ICON_EXTENSION,
    BuiltinCategoryManager,
)
from internal.core.tools.builtin_tools.provider import Provider

logger = logging.getLogger(__name__)


@inject.autoparams()
@dataclass
class BuiltinService:
    """内置插件服务层，把插件实体整理成前端可直接使用的 JSON 结构。"""

    provider_manager: BuiltinProviderManager
    category_manager: BuiltinCategoryManager

    def get_tool_inputs(self, tool_instance: BaseTool | None) -> list[dict]:
        """根据工具实例解析出入参描述列表。"""
        if tool_instance is None:
            return []
        # 工具的入参协议由 args_schema 生成，properties 即参数集合
        schema = tool_instance.get_input_jsonschema()
        properties = schema.get("properties") or {}
        required = schema.get("required") or []
        return [
            {
                "name": name,
                "description": prop.get("description", ""),
                "required": name in required,
                "type": prop.get("type", "string"),
            }
            for name, prop in properties.items()
        ]

    def get_builtin_tools(self) -> list[dict]:
        """获取全部服务商及其工具信息。"""
        providers = self.provider_manager.get_providers()
        return [self._provider_to_dict(provider) for provider in providers]

    def get_provider_tool(self, provider_name: str, tool_name: str) -> dict | None:
        """获取指定服务商下指定工具的信息，服务商或工具不存在时返回 None。"""
        provider = self.provider_manager.get_provider(provider_name)
        if provider is None:
            return None
        tool_entity = provider.get_tool_entity(tool_name)
        if tool_entity is None:
            return None
        entity = provider.entity
        inputs = self.get_tool_inputs(self._tool_instance(provider, tool_name))
        return {
            "provider": {
                "name": entity.name,
                "label": entity.label,
                "description": entity.description,
                "background": entity.background,
                "category": entity.category,
            },
            "name": tool_entity.name,
            "label": tool_entity.label,
            "description": tool_entity.description,
            "inputs": inputs,
            "params": [param.to_dict() for param in tool_entity.params],
            "created_at": entity.created_at,
        }

    def get_provider_icon(self, provider_name: str) -> bytes | None:
        """读取服务商图标文件的字节数据，服务商或图标不存在时返回 None。"""
        provider = self.provider_manager.get_provider(provider_name)
        if provider is None:
            return None
        icon = provider.entity.icon
        # 图标强制使用 svg 格式，与插件广场的分类图标约定一致
        if os.path.splitext(icon)[1].lower() != ICON_EXTENSION:
            return None
        icon_path = os.path.join(provider.asset_directory, icon)
        if not os.path.isfile(icon_path):
            return None
        # 以字节返回给前端，供 img 标签直接展示
        with open(icon_path, "rb") as file:
            return file.read()

    def get_categories(self) -> list[dict]:
        """获取插件广场的全部分类信息。"""
        categories = self.category_manager.get_categories()
        return [category.to_dict() for category in categories]

    def _provider_to_dict(self, provider: Provider) -> dict:
        """把服务商实体连同其工具整理成一条 JSON 数据。"""
        entity = provider.entity
        return {
            "name": entity.name,
            "label": entity.label,
            "description": entity.description,
            "background": entity.background,
            "category": entity.category,
            "created_at": entity.created_at,
            "tools": [
                {
                    "name": tool_entity.name,
                    "label": tool_entity.label,
                    "description": tool_entity.description,
                    "inputs": self.get_tool_inputs(
                        self._tool_instance(provider, tool_entity.name)
                    ),
                    "params": [param.to_dict() for param in tool_entity.params],
                }
                for tool_entity in provider.get_tool_entities()
            ],
        }

    def _tool_instance(self, provider: Provider, tool_name: str) -> BaseTool | None:
        # 个别工具实例化可能依赖密钥等外部条件，单个插件失败不应影响整体列表
        try:
            return provider.get_tool_instance(tool_name)
        except Exception as error:
            logger.exception(
                "内置工具 %s/%s 实例化失败", provider.entity.name, tool_name
            )
            return None


__all__ = ["BuiltinService"]
