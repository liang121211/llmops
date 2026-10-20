import json
from types import SimpleNamespace

import pytest
from langchain_core.tools import BaseTool

from internal.core.tools.builtin_tools import BuiltinProviderManager, Provider
from internal.core.tools.builtin_tools.entities import (
    ToolEntity,
    ToolParamType,
)
from internal.core.tools.builtin_tools.providers.gaode import (
    gaode_weather as gaode_weather_module,
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
        "gaode",
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


def test_gaode_provider_loads_weather_tool(manager):
    provider = manager.get_provider("gaode")

    assert {item.name for item in provider.get_tool_entities()} == {"gaode_weather"}
    entity = provider.get_tool_entity("gaode_weather")
    assert entity.label == "高德天气查询"
    # 实例化参数只有 key 与超时，城市是调用时由大模型给出的
    assert {param.name for param in entity.params} == {"api_key", "timeout"}
    tool = provider.get_tool_instance("gaode_weather")
    assert isinstance(tool, BaseTool)
    assert tool.name == "gaode_weather"


LIVE_PAYLOAD = {
    "status": "1",
    "info": "OK",
    "lives": [
        {
            "province": "浙江",
            "city": "杭州市",
            "weather": "雾",
            "temperature": "22",
            "winddirection": "西北",
            "windpower": "≤3",
            "humidity": "86",
            "reporttime": "2026-10-19 20:02:42",
        }
    ],
}

FORECAST_PAYLOAD = {
    "status": "1",
    "info": "OK",
    "forecasts": [
        {
            "city": "杭州市",
            "province": "浙江",
            "reporttime": "2026-10-19 20:02:42",
            "casts": [
                {
                    "date": "2026-10-20",
                    "dayweather": "小雨",
                    "nightweather": "小雨",
                    "daytemp": "31",
                    "nighttemp": "18",
                    "daywind": "西南",
                    "daypower": "1-3",
                }
            ],
        }
    ],
}


class TestGaodeWeatherTool:
    """高德天气工具：请求参数、文本整理与失败兜底，全部打桩不发真实请求。"""

    def _patch_requests(self, monkeypatch, payload=None, error=None):
        """替换模块里的 requests，记录调用参数并返回预设响应。"""
        captured = {}

        def fake_get(url, params=None, timeout=None):
            captured["url"] = url
            captured["params"] = params
            captured["timeout"] = timeout
            if error is not None:
                raise error
            return SimpleNamespace(
                status_code=200,
                text=json.dumps(payload or {}),
                json=lambda: payload or {},
            )

        monkeypatch.setattr(gaode_weather_module, "requests", SimpleNamespace(get=fake_get))
        return captured

    def test_live_weather_text(self, monkeypatch):
        captured = self._patch_requests(monkeypatch, LIVE_PAYLOAD)
        result = gaode_weather_module._query_weather("杭州", False, "test-key", 10)

        assert captured["params"]["extensions"] == "base"
        assert captured["params"]["city"] == "杭州"
        assert captured["params"]["key"] == "test-key"
        assert "杭州市（浙江）实时天气：雾，气温 22℃" in result
        assert "湿度 86%" in result

    def test_forecast_uses_extensions_all(self, monkeypatch):
        captured = self._patch_requests(monkeypatch, FORECAST_PAYLOAD)
        result = gaode_weather_module._query_weather("330100", True, "test-key", 10)

        assert captured["params"]["extensions"] == "all"
        assert "2026-10-20：白天 小雨，夜间 小雨，18~31℃" in result

    def test_empty_city_list_returns_hint(self, monkeypatch):
        self._patch_requests(monkeypatch, {"status": "1", "info": "OK", "lives": []})
        result = gaode_weather_module._query_weather("不存在的城市", False, "test-key", 10)
        assert result == "未查询到 不存在的城市 的实时天气"

    def test_status_zero_returns_reason(self, monkeypatch):
        self._patch_requests(monkeypatch, {"status": "0", "info": "INVALID_USER_KEY"})
        result = gaode_weather_module._query_weather("杭州", False, "test-key", 10)
        assert "高德天气查询失败：INVALID_USER_KEY" in result

    def test_request_exception_returns_reason(self, monkeypatch):
        self._patch_requests(monkeypatch, error=TimeoutError("超时"))
        result = gaode_weather_module._query_weather("杭州", False, "test-key", 10)
        assert "高德天气请求失败：超时" in result

    def test_missing_key_skips_request(self, monkeypatch):
        captured = self._patch_requests(monkeypatch, LIVE_PAYLOAD)
        monkeypatch.delenv("GAODE_API_KEY", raising=False)

        result = gaode_weather_module.gaode_weather().invoke({"city": "杭州"})

        assert "未配置高德天气的 GAODE_API_KEY" in result
        assert captured == {}

    def test_factory_reads_key_from_env(self, monkeypatch):
        captured = self._patch_requests(monkeypatch, LIVE_PAYLOAD)
        monkeypatch.setenv("GAODE_API_KEY", "env-key")

        result = gaode_weather_module.gaode_weather(timeout=8).invoke({"city": "杭州"})

        # 配置留空时回落到 .env 的 key
        assert captured["params"]["key"] == "env-key"
        assert captured["timeout"] == 8
        assert "杭州市" in result
