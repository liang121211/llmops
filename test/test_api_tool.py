import json

import inject
import pytest

from internal.core.tools.api_tools import OpenAPISchema, ToolEntity, ToolParam
from internal.exception import FailException
from internal.pkg.response import HttpCode
from internal.service.api_tool_service import ApiToolService

VALIDATE_SCHEMA_URL = "/api-tools/validate-openapi-schema"

# 教程示例：有道词典的 openapi 规范字符串
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


def valid_schema(**overrides) -> dict:
    """基于合法示例生成可覆盖的规范字典。"""
    schema = json.loads(json.dumps(YOUDAO_SCHEMA, ensure_ascii=False))
    schema.update(overrides)
    return schema


def load(content):
    """走服务层同样的解析入口。"""
    return OpenAPISchema.from_content(content)


def test_api_tool_service_is_injectable():
    service = inject.instance(ApiToolService)

    schema = service.load_openapi_schema(json.dumps(YOUDAO_SCHEMA, ensure_ascii=False))

    assert isinstance(schema, OpenAPISchema)
    assert schema.server == "https://dict.youdao.com"


def test_load_openapi_schema_accepts_dict():
    schema = load(YOUDAO_SCHEMA)

    assert schema.description == "这是一个查询对应英文单词字典的工具"
    assert [tool.name for tool in schema.tools] == ["YoudaoSuggest"]
    # 校验通过的原始 paths 会同步回实例
    assert set(schema.paths) == {"/suggest"}


def test_load_openapi_schema_parses_tool_fields():
    tool = load(YOUDAO_SCHEMA).tools[0]

    assert isinstance(tool, ToolEntity)
    assert (tool.name, tool.url, tool.method) == ("YoudaoSuggest", "/suggest", "get")
    assert tool.description == "根据传递的单词查询其字典信息"
    assert [param.name for param in tool.parameters] == ["q", "doctype"]
    assert tool.parameters[0].location == "query"
    assert tool.parameters[0].required is True
    assert tool.parameters[1].required is False


def test_load_openapi_schema_without_parameters():
    schema = valid_schema(
        paths={"/suggest": {"get": {"description": "查询字典", "operationId": "Suggest"}}}
    )

    assert load(schema).tools[0].parameters == []


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("not-json", "openapi_schema不是合法的JSON字符串"),
        ('"just-a-string"', "openapi_schema解析后必须是JSON对象"),
        ("[1, 2]", "openapi_schema解析后必须是JSON对象"),
    ],
)
def test_load_openapi_schema_rejects_bad_content(content, message):
    with pytest.raises(FailException, match=message):
        load(content)


def test_check_server_requires_string():
    with pytest.raises(FailException, match="缺少server字段或server不是字符串"):
        load(valid_schema(server=None))
    with pytest.raises(FailException, match="缺少server字段或server不是字符串"):
        load(valid_schema(server=""))
    with pytest.raises(FailException, match="缺少server字段或server不是字符串"):
        load(valid_schema(server=123))
    with pytest.raises(FailException, match="缺少server字段或server不是字符串"):
        load({"description": "缺少服务地址", "paths": {"/a": {"get": {}}}})


def test_check_description_requires_string():
    with pytest.raises(FailException, match="缺少description字段或description不是字符串"):
        load(valid_schema(description=None))
    with pytest.raises(FailException, match="缺少description字段或description不是字符串"):
        load(valid_schema(description=""))


def test_check_paths_requires_dict():
    with pytest.raises(FailException, match="缺少paths字段或paths不是字典"):
        load(valid_schema(paths=None))
    with pytest.raises(FailException, match="缺少paths字段或paths不是字典"):
        load(valid_schema(paths=[]))


def test_check_paths_rejects_path_not_start_with_slash():
    with pytest.raises(FailException, match="接口路径 suggest 必须以 / 开头"):
        load(valid_schema(paths={"suggest": {"get": {"description": "d", "operationId": "A"}}}))


def test_check_paths_rejects_non_dict_methods():
    with pytest.raises(FailException, match="/suggest 对应的数据必须是字典"):
        load(valid_schema(paths={"/suggest": "get"}))


def test_check_paths_rejects_empty_methods():
    with pytest.raises(FailException, match="/suggest 没有配置任何请求方式"):
        load(valid_schema(paths={"/suggest": {}}))


def test_check_paths_rejects_unsupported_method():
    schema = valid_schema(
        paths={
            "/suggest": {
                "delete": {"description": "删除", "operationId": "DeleteSuggest"}
            }
        }
    )

    with pytest.raises(FailException, match="的请求方式 delete 不被支持"):
        load(schema)


def test_check_paths_rejects_duplicate_operation_id():
    operation = {"description": "查询字典", "operationId": "YoudaoSuggest"}
    schema = valid_schema(paths={"/suggest": {"get": operation}, "/dict": {"post": operation}})

    with pytest.raises(FailException, match="存在重复的operationId：YoudaoSuggest"):
        load(schema)


def test_check_operation_requires_dict():
    with pytest.raises(FailException, match="/suggest 的 get 配置必须是字典"):
        load(valid_schema(paths={"/suggest": {"get": "YoudaoSuggest"}}))


def test_check_operation_requires_operation_id():
    with pytest.raises(FailException, match="/suggest 的 get 缺少operationId"):
        load(valid_schema(paths={"/suggest": {"get": {"description": "查询字典"}}}))


def test_check_operation_requires_description():
    with pytest.raises(FailException, match="/suggest 的 get 缺少description"):
        load(
            valid_schema(
                paths={"/suggest": {"get": {"operationId": "YoudaoSuggest"}}}
            )
        )


def test_check_parameters_requires_list():
    with pytest.raises(FailException, match="工具 YoudaoSuggest 的parameters必须是列表"):
        load(
            valid_schema(
                paths={
                    "/suggest": {
                        "get": {
                            "description": "查询字典",
                            "operationId": "YoudaoSuggest",
                            "parameters": {"name": "q"},
                        }
                    }
                }
            )
        )


def test_check_parameters_rejects_non_dict_item():
    with pytest.raises(FailException, match="第 1 个参数配置必须是字典"):
        load(
            valid_schema(
                paths={
                    "/suggest": {
                        "get": {
                            "description": "查询字典",
                            "operationId": "YoudaoSuggest",
                            "parameters": ["q"],
                        }
                    }
                }
            )
        )


def _schema_with_parameter(parameter: dict) -> dict:
    return valid_schema(
        paths={
            "/suggest": {
                "get": {
                    "description": "查询字典",
                    "operationId": "YoudaoSuggest",
                    "parameters": [parameter],
                }
            }
        }
    )


BASE_PARAM = {
    "name": "q",
    "in": "query",
    "description": "要查询的单词",
    "required": True,
    "type": "str",
}


@pytest.mark.parametrize(
    ("broken_key", "broken_value", "message"),
    [
        ("name", "", "参数缺少name或name不是字符串"),
        ("in", "body", "参数 q 的in取值不合法"),
        ("description", None, "参数 q 缺少description或类型不是字符串"),
        ("required", "true", "参数 q 缺少required或类型不是布尔值"),
        ("type", "string", "参数 q 的type取值不合法"),
    ],
)
def test_check_parameters_rejects_broken_parameter(
    broken_key, broken_value, message
):
    parameter = dict(BASE_PARAM)
    parameter[broken_key] = broken_value

    with pytest.raises(FailException, match=message):
        load(_schema_with_parameter(parameter))


@pytest.mark.parametrize("location", ["path", "query", "header", "cookie", "request_body"])
def test_check_parameters_accepts_all_locations(location):
    parameter = dict(BASE_PARAM, **{"in": location})

    tool = load(_schema_with_parameter(parameter)).tools[0]

    assert tool.parameters[0].location == location


@pytest.mark.parametrize("param_type", ["str", "int", "float", "bool"])
def test_check_parameters_accepts_all_types(param_type):
    parameter = dict(BASE_PARAM, **{"type": param_type})

    tool = load(_schema_with_parameter(parameter)).tools[0]

    assert tool.parameters[0].type == param_type


def test_check_returns_self_and_keeps_original_schema():
    instance = OpenAPISchema(YOUDAO_SCHEMA)

    result = instance.check()

    assert result is instance
    assert instance.openapi_schema == YOUDAO_SCHEMA
    assert instance.tools == [
        ToolEntity(
            name="YoudaoSuggest",
            description="根据传递的单词查询其字典信息",
            url="/suggest",
            method="get",
            parameters=[
                ToolParam(
                    name="q",
                    location="query",
                    description="要检索查询的单词，例如love/computer",
                    required=True,
                    type="str",
                ),
                ToolParam(
                    name="doctype",
                    location="query",
                    description="返回的数据类型，支持json和xml两种格式，默认情况下json数据",
                    required=False,
                    type="str",
                ),
            ],
        )
    ]


def test_validate_openapi_schema_endpoint(client):
    response = client.post(
        VALIDATE_SCHEMA_URL,
        json={"openapi_schema": json.dumps(YOUDAO_SCHEMA, ensure_ascii=False)},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["code"] == HttpCode.SUCCESS.value
    data = payload["data"]
    assert set(data) == {"server", "description", "tools"}
    assert data["server"] == "https://dict.youdao.com"
    assert data["description"] == "这是一个查询对应英文单词字典的工具"
    tool = data["tools"][0]
    assert set(tool) == {"name", "description", "url", "method", "parameters"}
    assert tool["name"] == "YoudaoSuggest"
    assert tool["url"] == "/suggest"
    assert tool["method"] == "get"
    # 响应里的参数位置沿用 openapi 规范的 in 字段
    assert set(tool["parameters"][0]) == {"name", "in", "description", "required", "type"}
    assert tool["parameters"][0]["in"] == "query"
    assert tool["parameters"][0]["required"] is True


def test_validate_openapi_schema_endpoint_requires_parameter(client):
    response = client.post(VALIDATE_SCHEMA_URL, json={})

    payload = response.get_json()
    assert payload["code"] == HttpCode.VALIDATE_ERROR.value
    assert payload["message"] == "openapi_schema参数必须传递"


def test_validate_openapi_schema_endpoint_rejects_invalid_json(client):
    response = client.post(VALIDATE_SCHEMA_URL, json={"openapi_schema": "not-a-json"})

    payload = response.get_json()
    assert payload["code"] == HttpCode.FAIL.value
    assert "openapi_schema不是合法的JSON字符串" in payload["message"]


def test_validate_openapi_schema_endpoint_reports_schema_error(client):
    broken = valid_schema()
    del broken["paths"]

    response = client.post(
        VALIDATE_SCHEMA_URL,
        json={"openapi_schema": json.dumps(broken, ensure_ascii=False)},
    )

    payload = response.get_json()
    assert payload["code"] == HttpCode.FAIL.value
    assert payload["message"] == "openapi_schema缺少paths字段或paths不是字典"


def test_validate_openapi_schema_endpoint_accepts_empty_paths(client):
    # 规范只要求 paths 是字典，空字典表示没有可用工具，解析结果为空列表
    response = client.post(
        VALIDATE_SCHEMA_URL,
        json={"openapi_schema": json.dumps(valid_schema(paths={}), ensure_ascii=False)},
    )

    payload = response.get_json()
    assert payload["code"] == HttpCode.SUCCESS.value
    assert payload["data"]["tools"] == []
