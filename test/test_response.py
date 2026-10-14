import pytest

from internal.pkg.response import (
    HttpCode,
    Response,
    fail_json,
    fail_message,
    forbidden_message,
    json,
    message,
    not_found_message,
    success_json,
    success_message,
    unauthorized_message,
    validate_error_json,
)


def get_body(result):
    """响应助手返回 (flask_response, status) 元组，拆出状态码与 JSON 体。"""
    response, status = result
    return status, response.get_json()


def test_response_defaults():
    data = Response()

    assert data.code is HttpCode.SUCCESS
    assert data.message == ""
    assert data.data == {}


def test_json_returns_flask_response(app_context):
    status, body = get_body(
        json(Response(code=HttpCode.FAIL, message="m", data={"a": 1}))
    )

    assert status == 200
    assert body == {"code": "fail", "message": "m", "data": {"a": 1}}


def test_success_json(app_context):
    status, body = get_body(success_json({"content": "hi"}))

    assert status == 200
    assert body == {"code": "success", "message": "", "data": {"content": "hi"}}


def test_success_json_without_data_returns_none(app_context):
    status, body = get_body(success_json())

    assert status == 200
    assert body["data"] is None


def test_fail_json(app_context):
    status, body = get_body(fail_json({"id": 1}))

    assert status == 200
    assert body == {"code": "fail", "message": "", "data": {"id": 1}}


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        ({}, ""),
        ({"query": ["query参数必须传递", "第二条错误"]}, "query参数必须传递"),
        ({"query": []}, ""),
        ({"name": "字段格式错误"}, "字段格式错误"),
    ],
)
def test_validate_error_json_uses_first_message(app_context, error, expected):
    status, body = get_body(validate_error_json(error))

    assert status == 200
    assert body == {
        "code": "validate_error",
        "message": expected,
        "data": {},
    }


def test_message_builds_empty_data(app_context):
    status, body = get_body(message(HttpCode.NOT_FOUND, "missing"))

    assert status == 200
    assert body == {"code": "not_found", "message": "missing", "data": {}}


@pytest.mark.parametrize(
    ("func", "code"),
    [
        (success_message, HttpCode.SUCCESS),
        (fail_message, HttpCode.FAIL),
        (not_found_message, HttpCode.NOT_FOUND),
        (unauthorized_message, HttpCode.UNAUTHORIZED),
        (forbidden_message, HttpCode.FORBIDDEN),
    ],
)
def test_message_helpers_carry_their_own_code(app_context, func, code):
    status, body = get_body(func("提示内容"))

    assert status == 200
    assert body == {"code": code.value, "message": "提示内容", "data": {}}
