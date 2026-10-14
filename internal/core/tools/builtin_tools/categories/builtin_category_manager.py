import logging
import os
from dataclasses import dataclass, field

from internal.core.tools.builtin_tools.categories.category_entities import (
    CategoryEntity,
)
from internal.lib import load_yaml

logger = logging.getLogger(__name__)

# 分类配置文件与本文件同目录
CATEGORIES_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "categories.yaml"
)


@dataclass
class BuiltinCategoryManager:
    """插件广场分类管理器，负责读取 categories.yaml 并提供分类查询。"""

    categories: dict[str, CategoryEntity] = field(default_factory=dict)

    def init(self) -> "BuiltinCategoryManager":
        """加载全部分类，图标不是 svg 的分类直接跳过。"""
        self.categories.clear()
        for config in load_yaml(CATEGORIES_FILE) or []:
            category = CategoryEntity.from_config(config)
            if not category.check_icon_extension():
                logger.warning(
                    "分类 %s 的图标 %s 不是 svg，已跳过",
                    category.name,
                    category.icon,
                )
                continue
            self.categories[category.name] = category
        logger.info("插件分类加载完成：%d 个", len(self.categories))
        return self

    def get_category_map(self) -> dict[str, CategoryEntity]:
        """获取分类映射信息，键是分类标识。"""
        return self.categories

    def get_categories(self) -> list[CategoryEntity]:
        """获取全部分类，顺序与配置文件一致。"""
        return list(self.categories.values())

    def get_category(self, name: str) -> CategoryEntity | None:
        """按分类标识获取分类，不存在时返回 None。"""
        return self.categories.get(name)


__all__ = ["CATEGORIES_FILE", "BuiltinCategoryManager"]
