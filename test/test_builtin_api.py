import inject

from internal.core.tools.builtin_tools import (
    BuiltinCategoryManager,
    BuiltinProviderManager,
)
from internal.pkg.response import HttpCode
from internal.service.builtin_service import BuiltinService

PROVIDER_KEYS = {"name", "label", "description", "background", "category"}
TOOL_KEYS = {"name", "label", "description", "inputs", "params"}


def build_service():
    """服务层依赖已初始化的管理器，直接从注入容器取单例。"""
    return BuiltinService(
        provider_manager=inject.instance(BuiltinProviderManager),
        category_manager=inject.instance(BuiltinCategoryManager),
    )


def test_builtin_tools_returns_provider_and_tool_info(client):
    response = client.get("/builtin-tools")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["code"] == HttpCode.SUCCESS.value
    providers = payload["data"]
    assert isinstance(providers, list)
    google = next(item for item in providers if item["name"] == "google")
    assert PROVIDER_KEYS <= set(google)
    assert "icon" not in google
    assert {"created_at", "tools"} <= set(google)
    serper = next(tool for tool in google["tools"] if tool["name"] == "google_serper")
    assert set(serper) == TOOL_KEYS
    assert serper["inputs"] == [
        {
            "name": "query",
            "description": "需要检索的问题",
            "required": True,
            "type": "string",
        }
    ]


def test_builtin_tools_params_come_from_config(client):
    response = client.get("/builtin-tools")

    google = next(
        item for item in response.get_json()["data"] if item["name"] == "google"
    )
    test_tool = next(tool for tool in google["tools"] if tool["name"] == "google_test")
    params = {param["name"]: param for param in test_tool["params"]}
    assert params["channel"]["options"] == ["web", "image", "scholar"]
    assert params["channel"]["required"] is True
    assert (params["limit"]["min"], params["limit"]["max"]) == (1, 5)
    assert params["verbose"]["type"] == "bool"


def test_builtin_tools_degrades_when_tool_instance_fails(client, monkeypatch):
    manager = inject.instance(BuiltinProviderManager)
    provider = manager.get_provider("google")

    def broken_factory(**kwargs):
        raise ValueError("缺少密钥")

    monkeypatch.setitem(provider.factories, "google_test", broken_factory)
    response = client.get("/builtin-tools")

    google = next(
        item for item in response.get_json()["data"] if item["name"] == "google"
    )
    tools = {tool["name"]: tool for tool in google["tools"]}
    # 实例化失败只让该工具的 inputs 为空，不影响整体列表
    assert tools["google_test"]["inputs"] == []
    assert tools["google_test"]["params"]
    assert tools["google_serper"]["inputs"]


def test_provider_tool_detail(client):
    response = client.get("/builtin-tools/google/tools/google_serper")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["code"] == HttpCode.SUCCESS.value
    data = payload["data"]
    assert set(data) == {
        "provider",
        "name",
        "label",
        "description",
        "inputs",
        "params",
        "created_at",
    }
    assert set(data["provider"]) == PROVIDER_KEYS
    assert data["provider"]["name"] == "google"
    assert data["provider"]["category"] == "search"
    assert data["name"] == "google_serper"
    assert data["inputs"][0]["name"] == "query"


def test_provider_tool_unknown_provider(client):
    response = client.get("/builtin-tools/nope/tools/google_serper")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["code"] == HttpCode.NOT_FOUND.value
    assert payload["data"] == {}


def test_provider_tool_unknown_tool(client):
    response = client.get("/builtin-tools/google/tools/nope")

    assert response.get_json() == {
        "code": HttpCode.NOT_FOUND.value,
        "message": "内置工具 google/nope 不存在",
        "data": {},
    }


def test_get_provider_tool_payload_matches_list(client):
    service = build_service()

    detail = service.get_provider_tool("google", "google_test")
    providers = service.get_builtin_tools()
    google = next(item for item in providers if item["name"] == "google")
    listed = next(tool for tool in google["tools"] if tool["name"] == "google_test")

    assert detail["inputs"] == listed["inputs"]
    assert detail["params"] == listed["params"]
    assert detail["created_at"] == google["created_at"]


def test_get_tool_inputs_without_instance():
    assert build_service().get_tool_inputs(None) == []


def test_categories_endpoint(client):
    response = client.get("/builtin-tools/categories")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["code"] == HttpCode.SUCCESS.value
    categories = payload["data"]
    assert [item["name"] for item in categories] == [
        "search",
        "image",
        "writer",
        "data",
        "other",
    ]
    assert all(
        set(item)
        == {"name", "label", "icon", "description", "created_at"}
        for item in categories
    )
    # 分类图标强制 svg
    assert all(item["icon"].endswith(".svg") for item in categories)
    assert categories[0]["label"] == "检索"


def test_service_categories_match_endpoint(client):
    response = client.get("/builtin-tools/categories")

    assert build_service().get_categories() == response.get_json()["data"]


def test_provider_icon_endpoint(client):
    response = client.get("/builtin-tools/google/icon")

    assert response.status_code == 200
    assert response.mimetype == "image/svg+xml"
    # 返回的是图标字节，可直接给 img 标签使用，不套统一响应结构
    assert response.data.startswith(b"<svg")


def test_service_provider_icon_returns_bytes():
    icon = build_service().get_provider_icon("google")

    assert isinstance(icon, bytes)
    assert b"</svg>" in icon


def test_provider_icon_unknown_provider(client):
    response = client.get("/builtin-tools/not_exists/icon")

    assert response.get_json() == {
        "code": HttpCode.NOT_FOUND.value,
        "message": "提供商 not_exists 的图标不存在",
        "data": {},
    }


def test_provider_icon_missing_asset_file(client):
    # other_tool 目录下没有 _asset 图标文件
    response = client.get("/builtin-tools/other_tool/icon")

    assert response.get_json()["code"] == HttpCode.NOT_FOUND.value
    assert build_service().get_provider_icon("other_tool") is None
