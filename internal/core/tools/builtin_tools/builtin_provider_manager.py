import logging
from dataclasses import dataclass, field
from typing import Any

from langchain_core.tools import BaseTool

from internal.core.tools.builtin_tools.provider import PROVIDERS_FILE, Provider
from internal.lib import load_yaml

logger = logging.getLogger(__name__)


@dataclass
class BuiltinProviderManager:
    """内置插件管理器，Flask 启动时扫描 providers.yml 注册全部服务提供商。"""

    providers: dict[str, Provider] = field(default_factory=dict)

    def init(self) -> "BuiltinProviderManager":
        """读取 providers.yml，逐个初始化服务商并加载其下的工具。"""
        self.providers.clear()
        for config in load_yaml(PROVIDERS_FILE) or []:
            provider = Provider.from_config(config).init()
            self.providers[provider.entity.name] = provider
            logger.info(
                "内置插件加载完成：%s，分类 %s，工具 %d 个",
                provider.entity.name,
                provider.entity.category,
                len(provider.tools),
            )
        return self

    def get_providers(self) -> list[Provider]:
        """获取全部服务提供商。"""
        return list(self.providers.values())

    def get_provider(self, name: str) -> Provider | None:
        """按名称获取指定服务提供商。"""
        return self.providers.get(name)

    def get_tool_instance(
        self, provider_name: str, tool_name: str, **values: Any
    ) -> BaseTool | None:
        """获取指定服务商下指定工具的实例，服务商或工具不存在时返回 None。"""
        provider = self.providers.get(provider_name)
        if provider is None:
            return None
        return provider.get_tool_instance(tool_name, **values)


__all__ = ["BuiltinProviderManager"]
