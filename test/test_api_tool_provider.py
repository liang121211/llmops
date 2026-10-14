import json
import uuid

import inject
import pytest

from internal.pkg.response import HttpCode
from internal.service.api_tool_service import ApiToolService

# TODO: 等待授权认证模块完成后再进行切换调整
ACCOUNT_ID = "a666a888-8888-6666-1234-b9d69212aaaa"

PROVIDER_DETAIL_KEYS = {
    "id",
    "name",
    "icon",
    "description",
    "openapi_schema",
    "headers",
    "created_at",
}
PROVIDER_BRIEF_KEYS = {"id", "name", "icon", "description", "headers", "created_at"}
TOOL_DETAIL_KEYS = {"id", "name", "description", "inputs", "provider"}

# 预置数据里第一个提供商与它名下的工具
SEEDED_PROVIDER_NAME = "分页测试插件01"
SEEDED_TOOL_NAME = "SeedSuggest01"

DELETE_PAYLOAD = {
    "name": "删除测试插件",
    "icon": "https://example.com/static/api-tool/delete.png",
    "openapi_schema": json.dumps(
        {
            "description": "用于删除接口测试的工具",
            "server": "https://dict.youdao.com",
            "paths": {
                "/suggest": {
                    "get": {
                        "description": "根据传递的单词查询其字典信息",
                        "operationId": "DeleteSuggest",
                        "parameters": [
                            {
                                "name": "q",
                                "in": "query",
                                "description": "要检索查询的单词",
                                "required": True,
                                "type": "str",
                            }
                        ],
                    }
                }
            },
        },
        ensure_ascii=False,
    ),
    "headers": [{"key": "Authorization", "value": "Bearer delete-test-token"}],
}


def provider_url(provider_id) -> str:
    return f"/api-tools/{provider_id}"


def tool_url(provider_id, tool_name: str) -> str:
    return f"/api-tools/{provider_id}/tools/{tool_name}"


@pytest.fixture
def seeded_provider(app_context):
    """取一条预置的分页测试数据，只读用例共用，不做删除。"""
    return inject.instance(ApiToolService).get_provider(ACCOUNT_ID, SEEDED_PROVIDER_NAME)


def test_get_provider_detail(client, seeded_provider):
    response = client.get(provider_url(seeded_provider.id))

    payload = response.get_json()
    assert payload["code"] == HttpCode.SUCCESS.value
    data = payload["data"]
    assert set(data) == PROVIDER_DETAIL_KEYS
    assert data["id"] == str(seeded_provider.id)
    assert data["name"] == SEEDED_PROVIDER_NAME
    assert data["icon"].endswith("seed-01.png")
    assert data["description"] == "分页测试插件 01 提供的字典查询能力"
    # openapi_schema 返回解析后的字典，而不是原始字符串
    assert data["openapi_schema"]["server"] == "https://dict.youdao.com"
    assert list(data["openapi_schema"]["paths"]) == ["/suggest"]
    assert data["headers"] == [
        {"key": "Authorization", "value": "Bearer seed-token-01"}
    ]
    assert data["created_at"]


def test_get_provider_detail_not_found(client):
    provider_id = uuid.uuid4()

    payload = client.get(provider_url(provider_id)).get_json()

    assert payload["code"] == HttpCode.NOT_FOUND.value
    assert payload["message"] == f"API工具提供商 {provider_id} 不存在"


def test_get_provider_tool_detail(client, seeded_provider):
    response = client.get(tool_url(seeded_provider.id, SEEDED_TOOL_NAME))

    payload = response.get_json()
    assert payload["code"] == HttpCode.SUCCESS.value
    data = payload["data"]
    assert set(data) == TOOL_DETAIL_KEYS
    assert data["name"] == SEEDED_TOOL_NAME
    assert data["description"] == "根据传递的单词查询其字典信息"
    # inputs 就是工具的参数列表，保留 openapi 规范里的 in 字段
    assert [item["name"] for item in data["inputs"]] == ["q", "doctype"]
    assert data["inputs"][0]["in"] == "query"
    assert data["inputs"][0]["required"] is True
    provider = data["provider"]
    assert set(provider) == PROVIDER_BRIEF_KEYS
    assert "openapi_schema" not in provider
    assert provider["id"] == str(seeded_provider.id)
    assert provider["name"] == SEEDED_PROVIDER_NAME


def test_get_provider_tool_not_found(client, seeded_provider):
    payload = client.get(tool_url(seeded_provider.id, "不存在")).get_json()

    assert payload["code"] == HttpCode.NOT_FOUND.value
    assert payload["message"] == f"API工具 {seeded_provider.id}/不存在 不存在"


def test_get_tool_of_unknown_provider_not_found(client):
    provider_id = uuid.uuid4()

    payload = client.get(tool_url(provider_id, SEEDED_TOOL_NAME)).get_json()

    assert payload["code"] == HttpCode.NOT_FOUND.value
    assert payload["message"] == f"API工具 {provider_id}/{SEEDED_TOOL_NAME} 不存在"


def test_delete_provider_removes_provider_and_tools(client, app_context, clean_api_tools):
    created = client.post("/api-tools", json=DELETE_PAYLOAD).get_json()["data"]
    provider_id = created["id"]
    service = inject.instance(ApiToolService)

    payload = client.delete(provider_url(provider_id)).get_json()

    assert payload["code"] == HttpCode.SUCCESS.value
    assert payload["data"] == {"id": provider_id}
    # 提供商与其名下的工具一起被删除
    assert service.get_provider_by_id(ACCOUNT_ID, provider_id) is None
    assert service.get_tool(ACCOUNT_ID, provider_id, "DeleteSuggest") is None
    assert client.get(provider_url(provider_id)).get_json()["code"] == (
        HttpCode.NOT_FOUND.value
    )


def test_delete_provider_twice_returns_not_found(client, app_context, clean_api_tools):
    created = client.post("/api-tools", json=DELETE_PAYLOAD).get_json()["data"]

    first = client.delete(provider_url(created["id"])).get_json()
    second = client.delete(provider_url(created["id"])).get_json()

    assert first["code"] == HttpCode.SUCCESS.value
    assert second["code"] == HttpCode.NOT_FOUND.value


def test_delete_unknown_provider_not_found(client):
    provider_id = uuid.uuid4()

    payload = client.delete(provider_url(provider_id)).get_json()

    assert payload["code"] == HttpCode.NOT_FOUND.value
    assert payload["message"] == f"API工具提供商 {provider_id} 不存在"
