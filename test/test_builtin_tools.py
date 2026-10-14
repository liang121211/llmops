import pytest
from langchain_core.tools import BaseTool

from internal.core.tools.builtin_tools import BuiltinProviderManager, Provider
from internal.core.tools.builtin_tools.entities import (
    ToolEntity,
    ToolParamType,
)
from internal.lib import dynamic_import


@pytest.fixture(scope="module")
def manager():
    """扫描一次内置插件配置，供本文件所有用例复用。"""
    return BuiltinProviderManager().init()


def _test_params(manager) -> dict:
    """取出 google_test 工具按参数名索引的参数字典。"""
    entity = manager.get_provider("google").get_tool_entity("google_test")
    return {param.name: param for param in entity.params}


def test_dynamic_import_returns_symbol():
    assert dynamic_import("internal.lib.helper", "utc_now")() is not None


def test_dynamic_import_missing_symbol():
    with pytest.raises(ImportError):
        dynamic_import("internal.lib.helper", "not_exists")


def test_manager_loads_all_providers(manager):
    assert [item.entity.name for item in manager.get_providers()] == [
        "google",
        "other_tool",
    ]
    assert isinstance(manager.get_provider("google"), Provider)
    assert manager.get_provider("not_exists") is None


def test_provider_entity_fields(manager):
    entity = manager.get_provider("google").entity

    assert entity.label == "Google"
    assert entity.icon == "icon.svg"
    assert entity.background == "#E5E7EB"
    assert entity.category == "search"
    assert entity.created_at == 1722498386
    # 分类只保留标识，展示名由 categories 包的分类管理器负责
    assert entity.category == "search"


def test_provider_scans_position_and_tool_files(manager):
    provider = manager.get_provider("google")

    entities = provider.get_tool_entities()
    assert {item.name for item in entities} == {"google_serper", "google_test"}
    assert all(isinstance(item, ToolEntity) for item in entities)
    assert provider.get_tool_entity("google_serper").label == "谷歌搜索工具"
    assert provider.get_tool_entity("not_exists") is None
    # 目录名与服务商名保持一致
    assert provider.directory.endswith("google")


def test_tool_param_types_and_ranges(manager):
    params = _test_params(manager)

    assert params["prefix"].type == ToolParamType.STRING
    assert params["limit"].type == ToolParamType.NUMBER
    assert (params["limit"].min_value, params["limit"].max_value) == (1, 5)
    assert params["verbose"].type == ToolParamType.BOOL
    assert params["channel"].type == ToolParamType.SELECT
    assert params["channel"].options == ["web", "image", "scholar"]
    assert params["channel"].required is True
    assert params["channel"].default == "web"
    # 未声明 generate_name 时回落到参数名
    assert params["limit"].generate_name == "limit"


def test_tool_param_normalize(manager):
    limit = _test_params(manager)["limit"]

    assert limit.normalize(None) == 3
    assert limit.normalize(99) == 5
    assert limit.normalize(0) == 1
    assert limit.normalize(2) == 2


def test_tool_instance_uses_config_defaults(manager):
    tool = manager.get_provider("google").get_tool_instance("google_test")

    assert isinstance(tool, BaseTool)
    assert tool.name == "google_test"
    assert tool.invoke({"query": "你好"}) == (
        "[demo] channel=web limit=3 verbose=False query=你好"
    )


def test_tool_instance_overrides_params(manager):
    tool = manager.get_provider("google").get_tool_instance(
        "google_test", channel="scholar", limit=4, verbose=True, prefix="case"
    )

    assert "channel=scholar limit=4 verbose=True" in tool.invoke({"query": "hi"})


def test_serper_tool_params_are_clamped(manager):
    tool = manager.get_provider("google").get_tool_instance(
        "google_serper", num_results=99, language="en-US"
    )

    assert isinstance(tool, BaseTool)
    # num_results 超过 max 后被裁剪
    assert tool.api_wrapper.k == 10
    assert tool.api_wrapper.hl == "en-US"


def test_manager_get_tool_instance(manager):
    assert isinstance(manager.get_tool_instance("google", "google_test"), BaseTool)
    assert manager.get_tool_instance("not_exists", "google_test") is None
    assert manager.get_tool_instance("google", "not_exists") is None
