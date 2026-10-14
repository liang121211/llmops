import json
import uuid
from unittest.mock import patch

import pytest

from internal.pkg.response import HttpCode

# 被 patch 的 requests 就在管理器模块里，测试不会真的发起网络请求
REQUESTS_PATH = (
    "internal.core.tools.api_tools.provider.api_tool_provider_manager.requests"
)
SERVER = "https://dict.youdao.com"
TOOL_NAME = "InvokeSuggest"
UPSTREAM_RESULT = '{"suggest": "love"}'

INVOKE_PAYLOAD = {
    "name": "调用测试插件",
    "icon": "https://example.com/static/api-tool/invoke.png",
    "openapi_schema": json.dumps(
        {
            "description": "用于调用接口测试的工具",
            "server": SERVER,
            "paths": {
                "/suggest": {
                    "get": {
                        "description": "根据传递的单词查询其字典信息",
                        "operationId": TOOL_NAME,
                        "parameters": [
                            {
                                "name": "q",
                                "in": "query",
                                "description": "要检索查询的单词",
                                "required": True,
                                "type": "str",
                            },
                            {
                                "name": "doctype",
                                "in": "query",
                                "description": "返回的数据类型",
                                "required": False,
                                "type": "str",
                            },
                        ],
                    }
                }
            },
        },
        ensure_ascii=False,
    ),
    "headers": [{"key": "Authorization", "value": "Bearer invoke-token"}],
}


@pytest.fixture
def created_provider(client, clean_api_tools):
    """创建一条提供商数据，用例结束后由 clean_api_tools 清理。"""
    body = client.post("/api-tools", json=INVOKE_PAYLOAD).get_json()
    assert body["code"] == HttpCode.SUCCESS.value, body
    return body["data"]


def invoke_url(provider_id: str, tool_name: str = TOOL_NAME) -> str:
    return f"/api-tools/invoke/{provider_id}/{tool_name}"


def test_invoke_tool_requests_upstream_api(client, created_provider):
    with patch(REQUESTS_PATH) as mock_requests:
        mock_requests.request.return_value.text = UPSTREAM_RESULT

        body = client.post(
            invoke_url(created_provider["id"]), json={"q": "love", "doctype": "json"}
        ).get_json()

    assert body["code"] == HttpCode.SUCCESS.value
    assert body["data"] == {"result": UPSTREAM_RESULT}
    call_args = mock_requests.request.call_args
    # url 由提供商规范里的 server 加上工具的接口路径拼成
    assert call_args.args == ("get", f"{SERVER}/suggest")
    assert call_args.kwargs["params"] == {"q": "love", "doctype": "json"}
    # 提供商上配置的请求头会带到第三方接口
    assert call_args.kwargs["headers"] == {"Authorization": "Bearer invoke-token"}
    assert call_args.kwargs["json"] is None


def test_invoke_tool_skips_optional_params(client, created_provider):
    with patch(REQUESTS_PATH) as mock_requests:
        mock_requests.request.return_value.text = UPSTREAM_RESULT

        body = client.post(
            invoke_url(created_provider["id"]), json={"q": "love"}
        ).get_json()

    assert body["code"] == HttpCode.SUCCESS.value
    assert mock_requests.request.call_args.kwargs["params"] == {"q": "love"}


def test_invoke_tool_missing_required_param(client, created_provider):
    with patch(REQUESTS_PATH) as mock_requests:
        body = client.post(invoke_url(created_provider["id"]), json={}).get_json()

    assert body["code"] == HttpCode.VALIDATE_ERROR.value
    assert body["message"] == "q Field required"
    assert body["data"] == {}
    # 入参不合法时不应该发起真实请求
    mock_requests.request.assert_not_called()


def test_invoke_tool_rejects_wrong_param_type(client, created_provider):
    with patch(REQUESTS_PATH) as mock_requests:
        body = client.post(invoke_url(created_provider["id"]), json={"q": 1}).get_json()

    assert body["code"] == HttpCode.VALIDATE_ERROR.value
    assert body["message"].startswith("q ")
    mock_requests.request.assert_not_called()


def test_invoke_tool_with_non_object_body(client, created_provider):
    body = client.post(invoke_url(created_provider["id"]), json=["love"]).get_json()

    assert body["code"] == HttpCode.VALIDATE_ERROR.value
    assert body["message"] == "请求体必须是JSON对象"


def test_invoke_tool_reports_upstream_error(client, created_provider, monkeypatch):
    # .env 里 FLASK_DEBUG=true，开发模式下全局异常处理会把异常抛出来，
    # 这里按生产环境的配置验证上游报错被转成 fail 响应
    monkeypatch.setitem(client.application.config, "DEBUG", False)
    monkeypatch.setitem(client.application.config, "PROPAGATE_EXCEPTIONS", False)
    with patch(REQUESTS_PATH) as mock_requests:
        mock_requests.request.return_value.raise_for_status.side_effect = Exception(
            "500 Server Error: Internal Server Error"
        )

        body = client.post(
            invoke_url(created_provider["id"]), json={"q": "love"}
        ).get_json()

    assert body["code"] == HttpCode.FAIL.value
    assert "500 Server Error" in body["message"]


def test_invoke_unknown_tool_not_found(client, created_provider):
    body = client.post(invoke_url(created_provider["id"], "NoSuchTool")).get_json()

    assert body["code"] == HttpCode.NOT_FOUND.value
    assert body["message"] == f"API工具 {created_provider['id']}/NoSuchTool 不存在"


def test_invoke_tool_of_unknown_provider_not_found(client):
    provider_id = uuid.uuid4()

    body = client.post(invoke_url(str(provider_id))).get_json()

    assert body["code"] == HttpCode.NOT_FOUND.value
    assert body["message"] == f"API工具 {provider_id}/{TOOL_NAME} 不存在"
