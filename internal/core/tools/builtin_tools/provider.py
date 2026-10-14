import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable

from langchain_core.tools import BaseTool

from internal.core.tools.builtin_tools.entities.provider_entity import ProviderEntity
from internal.core.tools.builtin_tools.entities.tool_entity import ToolEntity
from internal.lib import dynamic_import, load_yaml

logger = logging.getLogger(__name__)

# 内置插件根目录，providers.yml 和 providers/ 目录都在这里
BUILTIN_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
PROVIDERS_DIR = os.path.join(BUILTIN_TOOLS_DIR, "providers")
PROVIDERS_FILE = os.path.join(BUILTIN_TOOLS_DIR, "providers.yml")
# 工具工厂函数所在的包前缀
PROVIDERS_PACKAGE = f"{__package__}.providers"


@dataclass
class Provider:
    """服务提供商，负责扫描自己的目录并动态加载目录下的工具。"""

    entity: ProviderEntity
    tools: dict[str, ToolEntity] = field(default_factory=dict)
    factories: dict[str, Callable] = field(default_factory=dict)

    @classmethod
    def from_config(cls, config: dict) -> "Provider":
        """按 providers.yml 里的一条配置创建服务商。"""
        return cls(entity=ProviderEntity.from_config(config))

    @property
    def directory(self) -> str:
        """服务商目录，里面有 position.yml 以及每个工具同名的 yml 和 py 文件。"""
        return os.path.join(PROVIDERS_DIR, self.entity.name)

    @property
    def asset_directory(self) -> str:
        """服务商资源目录，图标等静态资源放在 providers/<name>/_asset 下。"""
        return os.path.join(self.directory, "_asset")

    def init(self) -> "Provider":
        """扫描 position.yml，加载每个工具的配置实体与工厂函数。"""
        self.tools.clear()
        self.factories.clear()

        position_file = os.path.join(self.directory, "position.yml")
        if not os.path.isfile(position_file):
            logger.warning("服务商 %s 缺少 position.yml，已跳过", self.entity.name)
            return self

        for tool_name in load_yaml(position_file) or []:
            tool_config = load_yaml(os.path.join(self.directory, f"{tool_name}.yml"))
            self.tools[tool_name] = ToolEntity.from_config(tool_config or {})
            # 约定：工具名 == yml 文件名 == py 文件名 == 工厂函数名
            self.factories[tool_name] = dynamic_import(
                f"{PROVIDERS_PACKAGE}.{self.entity.name}.{tool_name}", tool_name
            )
        return self

    def get_tool_instance(self, name: str, **values: Any) -> BaseTool | None:
        """实例化工具，未传的参数使用配置里的默认值。"""
        factory = self.factories.get(name)
        if factory is None:
            return None
        # 只把配置中声明过的参数交给工厂，取值先做默认值回落与范围裁剪
        kwargs = {
            param.name: param.normalize(values.get(param.name))
            for param in self.tools[name].params
        }
        return factory(**kwargs)

    def get_tool_entity(self, name: str) -> ToolEntity | None:
        """按工具名获取工具实体。"""
        return self.tools.get(name)

    def get_tool_entities(self) -> list[ToolEntity]:
        """获取该服务商下的全部工具实体。"""
        return list(self.tools.values())


__all__ = [
    "BUILTIN_TOOLS_DIR",
    "PROVIDERS_DIR",
    "PROVIDERS_FILE",
    "PROVIDERS_PACKAGE",
    "Provider",
]
