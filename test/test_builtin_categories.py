import os

import pytest

from internal.core.tools.builtin_tools import BuiltinCategoryManager, CategoryEntity
from internal.core.tools.builtin_tools.categories import (
    CATEGORIES_FILE,
    builtin_category_manager as category_module,
)

CATEGORY_KEYS = {"name", "label", "icon", "description", "created_at"}


@pytest.fixture(scope="module")
def category_manager():
    """分类配置文件只需扫描一次，供本文件所有用例复用。"""
    return BuiltinCategoryManager().init()


def test_categories_file_exists():
    assert CATEGORIES_FILE.endswith("categories.yaml")
    assert os.path.isfile(CATEGORIES_FILE)


def test_category_entity_check_icon_extension():
    assert CategoryEntity(name="search", icon="search.svg").check_icon_extension()
    # 强制 svg：后缀大小写都接受，其它格式一律不合法
    assert CategoryEntity(icon="SEARCH.SVG").check_icon_extension()
    assert not CategoryEntity(icon="search.png").check_icon_extension()
    assert not CategoryEntity(icon="").check_icon_extension()


def test_category_entity_from_config():
    entity = CategoryEntity.from_config(
        {
            "name": "search",
            "label": "检索",
            "icon": "search.svg",
            "description": "检索类工具",
            "created_at": "1722498386",
        }
    )

    assert entity.name == "search"
    assert entity.label == "检索"
    # created_at 在 YAML 里可能被写成字符串，实体统一转成整数
    assert entity.created_at == 1722498386
    assert set(entity.to_dict()) == CATEGORY_KEYS


def test_category_entity_from_empty_config():
    entity = CategoryEntity.from_config({})

    assert entity.name == ""
    assert entity.created_at == 0
    assert not entity.check_icon_extension()


def test_manager_loads_category_map(category_manager):
    category_map = category_manager.get_category_map()

    assert set(category_map) == {"search", "image", "writer", "data", "other"}
    assert isinstance(category_map["search"], CategoryEntity)
    assert category_map["search"].label == "检索"
    assert category_map["other"].label == "其它"
    # 分类顺序与 categories.yaml 里的书写顺序一致
    assert [item.name for item in category_manager.get_categories()] == [
        "search",
        "image",
        "writer",
        "data",
        "other",
    ]
    assert category_manager.get_category("search").icon == "search.svg"
    assert category_manager.get_category("not_exists") is None


def test_manager_skips_non_svg_icon(category_manager, monkeypatch):
    monkeypatch.setattr(
        category_module,
        "load_yaml",
        lambda _: [
            {"name": "search", "label": "检索", "icon": "search.svg"},
            {"name": "bad", "label": "非法图标", "icon": "bad.png"},
        ],
    )

    manager = BuiltinCategoryManager().init()

    # 图标不是 svg 的分类不会被加载进分类表
    assert set(manager.get_category_map()) == {"search"}
    assert manager.get_category("bad") is None
    # 共享的分类管理器不受影响
    assert "search" in category_manager.get_category_map()


def test_manager_init_rebuilds_category_map(monkeypatch):
    manager = BuiltinCategoryManager().init()
    before = dict(manager.get_category_map())

    monkeypatch.setattr(
        category_module, "load_yaml", lambda _: [{"name": "only", "icon": "only.svg"}]
    )
    manager.init()

    assert set(manager.get_category_map()) == {"only"}
    assert before != manager.get_category_map()
