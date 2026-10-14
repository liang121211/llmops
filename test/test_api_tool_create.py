import json
import uuid

import inject
import pytest
from sqlalchemy import select

from internal.exception import FailException
from internal.model import ApiTool, ApiToolProvider
from internal.pkg.response import HttpCode
from internal.service.api_tool_service import ApiToolService

CREATE_URL = "/api-tools"

# TODO: 等待授权认证模块完成后再进行切换调整
ACCOUNT_ID = "a666a888-8888-6666-1234-b9d69212aaaa"
ICON_URL = (
    "https://llmops09-1258402969.cos.ap-guangzhou.myqcloud.com/2026/05/12/test3.png"
)

# 教程示例：有道词典的 openapi 规范
YOUDAO_SCHEMA = {
    "description": "这是一个查询对应英文单词字典的工具",
    "server": "https://dict.youdao.com",
    "paths": {
        "/suggest": {
            "get": {
                "description": "根据传递的单词查询其字典信息",
                "operationId": "YoudaoSuggest",
                "parameters": [
                    {
                        "name": "q",
                        "in": "query",
                        "description": "要检索查询的单词，例如love/computer",
                        "required": True,
                        "type": "str",
                    },
                    {
                        "name": "doctype",
                        "in": "query",
                        "description": "返回的数据类型，支持json和xml两种格式，默认情况下json数据",
                        "required": False,
                        "type": "str",
                    },
                ],
            }
        }
    },
}

CREATE_PAYLOAD = {
    "name": "谷歌插件",
    "icon": ICON_URL,
    "openapi_schema": json.dumps(YOUDAO_SCHEMA, ensure_ascii=False),
    "headers": [{"key": "Authorization", "value": "Bearer test-token"}],
}


def create_args(**overrides) -> dict:
    """服务层创建参数的默认组合，便于用例覆盖单个字段。"""
    args = {
        "account_id": ACCOUNT_ID,
        "name": "谷歌插件",
        "icon": ICON_URL,
        "openapi_schema": CREATE_PAYLOAD["openapi_schema"],
        "headers": CREATE_PAYLOAD["headers"],
    }
    args.update(overrides)
    return args


@pytest.fixture
def api_tool_service():
    return inject.instance(ApiToolService)


def count_rows(api_tool_service, name: str) -> tuple[int, int]:
    """统计账号下指定名字的提供商数量，以及它们名下的工具数量。"""
    providers = api_tool_service.get_list(
        ApiToolProvider.account_id == ACCOUNT_ID, ApiToolProvider.name == name
    )
    if not providers:
        return 0, 0
    stmt = select(ApiTool).where(
        ApiTool.provider_id.in_([provider.id for provider in providers])
    )
    tools = api_tool_service.db.session.execute(stmt).scalars().all()
    return len(providers), len(tools)


def test_service_creates_provider_and_tools(api_tool_service, clean_api_tools):
    provider = api_tool_service.create_openapi_schema(**create_args())

    assert provider.name == "谷歌插件"
    assert provider.icon == ICON_URL
    # 提供商描述取规范里的 description
    assert provider.description == "这是一个查询对应英文单词字典的工具"
    assert provider.openapi_schema == YOUDAO_SCHEMA
    assert provider.header == [{"key": "Authorization", "value": "Bearer test-token"}]
    tools = provider.tools
    assert [tool.name for tool in tools] == ["YoudaoSuggest"]
    # 工具必须关联提供商 id 和同一个账号
    assert tools[0].provider_id == provider.id
    assert tools[0].account_id == uuid.UUID(ACCOUNT_ID)
    assert (tools[0].url, tools[0].method) == ("/suggest", "get")
    assert tools[0].parameters[0]["in"] == "query"


def test_service_defaults_headers_to_empty_list(api_tool_service, clean_api_tools):
    provider = api_tool_service.create_openapi_schema(
        **create_args(name="无请求头插件", headers=None)
    )

    assert provider.header == []


def test_service_rejects_duplicate_provider_name(api_tool_service, clean_api_tools):
    api_tool_service.create_openapi_schema(**create_args())

    with pytest.raises(FailException, match="API工具提供者 谷歌插件 已经存在"):
        api_tool_service.create_openapi_schema(**create_args())

    assert count_rows(api_tool_service, "谷歌插件") == (1, 1)


def test_service_writes_nothing_when_schema_invalid(api_tool_service, clean_api_tools):
    with pytest.raises(FailException, match="缺少server字段"):
        api_tool_service.create_openapi_schema(
            **create_args(
                openapi_schema=json.dumps(
                    {"description": "缺少服务地址", "paths": {"/a": {"get": {}}}},
                    ensure_ascii=False,
                )
            )
        )

    assert count_rows(api_tool_service, "坏规范插件") == (0, 0)


def test_create_openapi_schema_endpoint(client, clean_api_tools):
    response = client.post(CREATE_URL, json=CREATE_PAYLOAD)

    payload = response.get_json()
    assert payload["code"] == HttpCode.SUCCESS.value
    data = payload["data"]
    assert set(data) == {
        "id",
        "account_id",
        "name",
        "icon",
        "description",
        "headers",
        "updated_at",
        "created_at",
        "tools",
    }
    assert data["account_id"] == ACCOUNT_ID
    assert data["name"] == "谷歌插件"
    assert data["icon"] == ICON_URL
    assert data["description"] == "这是一个查询对应英文单词字典的工具"
    assert data["headers"] == [{"key": "Authorization", "value": "Bearer test-token"}]
    tool = data["tools"][0]
    assert set(tool) == {
        "id",
        "account_id",
        "provider_id",
        "name",
        "description",
        "url",
        "method",
        "parameters",
        "updated_at",
        "created_at",
    }
    assert tool["provider_id"] == data["id"]
    assert tool["name"] == "YoudaoSuggest"
    assert tool["url"] == "/suggest"
    assert tool["method"] == "get"
    assert tool["parameters"][0]["in"] == "query"


def test_create_openapi_schema_endpoint_rejects_duplicate_name(client, clean_api_tools):
    first = client.post(CREATE_URL, json=CREATE_PAYLOAD).get_json()
    assert first["code"] == HttpCode.SUCCESS.value

    body = client.post(CREATE_URL, json=CREATE_PAYLOAD).get_json()

    assert body["code"] == HttpCode.FAIL.value
    assert body["message"] == "API工具提供者 谷歌插件 已经存在"


@pytest.mark.parametrize(
    ("broken_key", "message"),
    [
        ("name", "name参数必须传递"),
        ("icon", "icon参数必须传递"),
        ("openapi_schema", "openapi_schema参数必须传递"),
    ],
)
def test_create_openapi_schema_endpoint_requires_parameters(client, broken_key, message):
    payload = dict(CREATE_PAYLOAD)
    del payload[broken_key]

    body = client.post(CREATE_URL, json=payload).get_json()

    assert body["code"] == HttpCode.VALIDATE_ERROR.value
    assert body["message"] == message


@pytest.mark.parametrize("icon", ["not-a-url", "/local/path.png"])
def test_create_openapi_schema_endpoint_requires_url_icon(client, icon):
    body = client.post(CREATE_URL, json=dict(CREATE_PAYLOAD, **{"icon": icon})).get_json()

    assert body["code"] == HttpCode.VALIDATE_ERROR.value
    assert body["message"] == "icon参数必须是URL格式的字符串"


def test_create_openapi_schema_endpoint_checks_name_length(client):
    body = client.post(CREATE_URL, json=dict(CREATE_PAYLOAD, **{"name": "名" * 65})).get_json()

    assert body["code"] == HttpCode.VALIDATE_ERROR.value
    assert body["message"] == "name参数长度为1-64个字符"


@pytest.mark.parametrize(
    ("headers", "message"),
    [
        (["Authorization"], "headers第 1 项必须是字典类型"),
        ([{"key": "Authorization"}], "headers第 1 项必须只包含key和value字段"),
        ([{"key": "", "value": "b"}], "headers第 1 项的key必须是非空字符串"),
        ([{"key": "a", "value": 1}], "headers第 1 项的value必须是字符串"),
        ({"key": "a", "value": "b"}, "headers参数必须是列表类型"),
        ("Authorization", "headers参数必须是列表类型"),
    ],
)
def test_create_openapi_schema_endpoint_checks_headers(client, headers, message):
    body = client.post(
        CREATE_URL, json=dict(CREATE_PAYLOAD, **{"headers": headers})
    ).get_json()

    assert body["code"] == HttpCode.VALIDATE_ERROR.value
    assert body["message"] == message


def test_create_openapi_schema_endpoint_allows_missing_headers(client, clean_api_tools):
    payload = dict(CREATE_PAYLOAD)
    del payload["headers"]

    body = client.post(CREATE_URL, json=payload).get_json()

    assert body["code"] == HttpCode.SUCCESS.value
    assert body["data"]["headers"] == []


def test_create_openapi_schema_endpoint_allows_empty_headers(client, clean_api_tools):
    payload = dict(CREATE_PAYLOAD, **{"name": "空请求头插件", "headers": []})

    body = client.post(CREATE_URL, json=payload).get_json()

    assert body["code"] == HttpCode.SUCCESS.value
    assert body["data"]["headers"] == []


def test_create_openapi_schema_endpoint_reports_schema_error(client, clean_api_tools):
    broken = dict(YOUDAO_SCHEMA)
    del broken["server"]
    payload = dict(
        CREATE_PAYLOAD, **{"openapi_schema": json.dumps(broken, ensure_ascii=False)}
    )

    body = client.post(CREATE_URL, json=payload).get_json()

    assert body["code"] == HttpCode.FAIL.value
    assert body["message"] == "openapi_schema缺少server字段或server不是字符串"
