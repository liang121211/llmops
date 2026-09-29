from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage

from internal.pkg.response import (
    HttpCode,
    fail_message,
    forbidden_message,
    not_found_message,
    success_message,
    unauthorized_message,
)


def test_ping(client):
    response = client.get("/ping")
    assert response.status_code == 200
    assert response.get_json() == {"ping": "pong"}


@patch("internal.handler.app_handler.ChatOpenAI")
def test_chat(mock_chat_openai, client):
    mock_model = MagicMock()
    mock_model.return_value = AIMessage("你好，我是智能体")
    mock_chat_openai.return_value = mock_model

    response = client.post("/app/chat", json={"query": "你好"})

    assert response.status_code == 200
    assert response.get_json() == {
        "code": HttpCode.SUCCESS.value,
        "message": "",
        "data": {"content": "你好，我是智能体"},
    }
    mock_chat_openai.assert_called_once_with(model="deepseek-v4-flash")


def test_chat_missing_query(client):
    response = client.post("/app/chat")

    assert response.status_code == 200
    assert response.get_json() == {
        "code": HttpCode.VALIDATE_ERROR.value,
        "message": "query参数必须传递",
        "data": {},
    }


def test_chat_query_too_long(client):
    response = client.post("/app/chat", json={"query": "a" * 2001})

    assert response.status_code == 200
    assert response.get_json() == {
        "code": HttpCode.VALIDATE_ERROR.value,
        "message": "query参数最大长度为2000字符",
        "data": {},
    }


def test_response_messages(app_context):
    responses = [
        (success_message("ok"), HttpCode.SUCCESS),
        (fail_message("failed"), HttpCode.FAIL),
        (not_found_message("missing"), HttpCode.NOT_FOUND),
        (unauthorized_message("login required"), HttpCode.UNAUTHORIZED),
        (forbidden_message("denied"), HttpCode.FORBIDDEN),
    ]

    for (response, status), code in responses:
        assert status == 200
        assert response.get_json()["code"] == code.value
