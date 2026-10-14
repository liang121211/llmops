from unittest.mock import patch

import pytest
from langchain_core.tools import BaseTool

from internal.core.tools.api_tools import (
    ApiProviderManager,
    ParameterIn,
    ParameterType,
    ParameterTypeMap,
    ToolEntity,
    ToolParam,
)
from internal.core.tools.api_tools.provider import REQUEST_TIMEOUT

# 被 patch 的 requests 就在管理器模块里，测试不会真的发起网络请求
REQUESTS_PATH = (
    "internal.core.tools.api_tools.provider.api_tool_provider_manager.requests"
)

# 参数位置与类型的枚举取值，取别名让用例更短
PATH = ParameterIn.PATH.value
QUERY = ParameterIn.QUERY.value
HEADER = ParameterIn.HEADER.value
COOKIE = ParameterIn.COOKIE.value
BODY = ParameterIn.REQUEST_BODY.value
STR = ParameterType.STR.value
INT = ParameterType.INT.value
FLOAT = ParameterType.FLOAT.value
BOOL = ParameterType.BOOL.value


def build_param(name: str, location: str, param_type: str, required: bool) -> ToolParam:
    return ToolParam(
        name=name,
        location=location,
        description=f"{name}的说明",
        required=required,
        type=param_type,
    )


def build_entity(parameters: list[ToolParam] = None, method: str = "get") -> ToolEntity:
    if parameters is None:
        parameters = [
            build_param("q", QUERY, STR, True),
            build_param("num", QUERY, INT, False),
        ]
    return ToolEntity(
        name="SeedSuggest",
        description="根据传递的单词查询其字典信息",
        url="https://dict.youdao.com/suggest",
        method=method,
        parameters=parameters,
    )


@pytest.fixture
def manager():
    return ApiProviderManager()


def invoke_with_mock(manager, entity, args: dict, headers: dict = None):
    """调用工具并返回 requests.request 的调用参数。"""
    with patch(REQUESTS_PATH) as mock_requests:
        mock_requests.request.return_value.text = '{"suggest": "love"}'
        result = manager.get_tool(entity, headers=headers).invoke(args)
    return result, mock_requests.request.call_args


def test_parameter_type_map_covers_all_types():
    assert ParameterTypeMap == {STR: str, INT: int, FLOAT: float, BOOL: bool}
    assert set(ParameterTypeMap) == {member.value for member in ParameterType}


def test_get_tool_returns_langchain_tool(manager):
    tool = manager.get_tool(build_entity())

    assert isinstance(tool, BaseTool)
    assert tool.name == "SeedSuggest"
    assert tool.description == "根据传递的单词查询其字典信息"


def test_args_schema_uses_declared_types(manager):
    entity = build_entity(
        [
            build_param("q", QUERY, STR, True),
            build_param("num", QUERY, INT, False),
            build_param("ratio", QUERY, FLOAT, False),
            build_param("verbose", QUERY, BOOL, False),
        ]
    )

    schema = manager.get_tool(entity).args_schema.model_json_schema()

    assert schema["required"] == ["q"]
    # 必填参数直接是声明的类型，选填参数允许为空并有默认值
    assert schema["properties"]["q"]["type"] == "string"
    assert schema["properties"]["q"]["description"] == "q的说明"
    assert {"type": "integer"} in schema["properties"]["num"]["anyOf"]
    assert schema["properties"]["num"]["default"] is None
    assert {"type": "number"} in schema["properties"]["ratio"]["anyOf"]
    assert {"type": "boolean"} in schema["properties"]["verbose"]["anyOf"]


def test_args_schema_rejects_missing_required_param(manager):
    tool = manager.get_tool(build_entity())

    with pytest.raises(Exception) as error:
        tool.invoke({"num": 3})

    assert "q" in str(error.value)


def test_generated_func_sends_get_request(manager):
    result, call_args = invoke_with_mock(
        manager, build_entity(), {"q": "love", "num": 3}
    )

    assert result == '{"suggest": "love"}'
    assert call_args.args == ("get", "https://dict.youdao.com/suggest")
    assert call_args.kwargs["params"] == {"q": "love", "num": 3}
    assert call_args.kwargs["timeout"] == REQUEST_TIMEOUT
    # 没有请求体参数时不能带上 JSON 体
    assert call_args.kwargs["json"] is None
    assert call_args.kwargs["cookies"] == {}


def test_generated_func_skips_params_not_passed(manager):
    _, call_args = invoke_with_mock(manager, build_entity(), {"q": "love"})

    assert call_args.kwargs["params"] == {"q": "love"}


def test_generated_func_sends_post_body(manager):
    entity = build_entity([build_param("word", BODY, STR, True)], method="post")

    _, call_args = invoke_with_mock(manager, entity, {"word": "love"})

    assert call_args.args == ("post", "https://dict.youdao.com/suggest")
    assert call_args.kwargs["json"] == {"word": "love"}
    assert call_args.kwargs["params"] == {}


def test_generated_func_replaces_path_params(manager):
    entity = build_entity(
        [
            build_param("word", PATH, STR, True),
            build_param("q", QUERY, STR, False),
        ]
    )
    entity.url = "https://dict.youdao.com/jsonapi_suggest/{word}"

    _, call_args = invoke_with_mock(manager, entity, {"word": "love", "q": "l"})

    assert call_args.args[1] == "https://dict.youdao.com/jsonapi_suggest/love"
    assert call_args.kwargs["params"] == {"q": "l"}


def test_generated_func_merges_provider_headers(manager):
    entity = build_entity([build_param("X-Trace", HEADER, STR, False)])

    _, call_args = invoke_with_mock(
        manager,
        entity,
        {"q": "love", "X-Trace": "from-call"},
        headers={"Authorization": "Bearer token", "X-Trace": "from-provider"},
    )

    # 提供商上的请求头始终带上，调用时传入的同名请求头优先
    assert call_args.kwargs["headers"] == {
        "Authorization": "Bearer token",
        "X-Trace": "from-call",
    }


def test_generated_func_sends_cookies(manager):
    entity = build_entity([build_param("session", COOKIE, STR, True)])

    _, call_args = invoke_with_mock(manager, entity, {"q": "love", "session": "abc"})

    assert call_args.kwargs["cookies"] == {"session": "abc"}


def test_generated_func_raises_on_http_error(manager):
    entity = build_entity()

    with patch(REQUESTS_PATH) as mock_requests:
        mock_requests.request.return_value.raise_for_status.side_effect = Exception(
            "500 Server Error"
        )
        tool = manager.get_tool(entity)

        with pytest.raises(Exception) as error:
            tool.invoke({"q": "love"})

    assert "500 Server Error" in str(error.value)


def test_generated_func_has_no_shared_state_between_tools(manager):
    first = manager.get_tool(build_entity(), headers={"Authorization": "Bearer one"})
    second = manager.get_tool(build_entity(method="post"), headers={})

    with patch(REQUESTS_PATH) as mock_requests:
        mock_requests.request.return_value.text = "ok"
        first.invoke({"q": "love"})
        first_headers = mock_requests.request.call_args.kwargs["headers"]
        second.invoke({"q": "love"})
        second_headers = mock_requests.request.call_args.kwargs["headers"]

    assert first_headers == {"Authorization": "Bearer one"}
    assert second_headers == {}
