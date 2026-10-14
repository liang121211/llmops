from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage

from internal.core.tools.builtin_tools import BuiltinProviderManager
from internal.pkg.response import HttpCode


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


@patch.object(BuiltinProviderManager, "get_tool_instance")
def test_builtin_tool_test_searches_with_query(mock_get_tool_instance, client):
    # 联网检索不在测试里真实发起，mock 掉工具实例的执行结果
    mock_tool = MagicMock()
    mock_tool.invoke.return_value = "杭州今天晴，气温 25 度。"
    mock_get_tool_instance.return_value = mock_tool

    response = client.post("/app/builtin_tool_test", json={"query": "杭州今天天气"})

    assert response.status_code == 200
    assert response.get_json() == {
        "code": HttpCode.SUCCESS.value,
        "message": "",
        "data": {"content": "杭州今天晴，气温 25 度。"},
    }
    mock_get_tool_instance.assert_called_once_with("google", "google_serper")
    mock_tool.invoke.assert_called_once_with({"query": "杭州今天天气"})


def test_builtin_tool_test_missing_query(client):
    response = client.post("/app/builtin_tool_test")

    assert response.status_code == 200
    assert response.get_json() == {
        "code": HttpCode.VALIDATE_ERROR.value,
        "message": "query参数必须传递",
        "data": {},
    }


@patch.object(BuiltinProviderManager, "get_tool_instance", return_value=None)
def test_builtin_tool_test_tool_unavailable(mock_get_tool_instance, client):
    response = client.post("/app/builtin_tool_test", json={"query": "你好"})

    assert response.status_code == 200
    assert response.get_json() == {
        "code": HttpCode.NOT_FOUND.value,
        "message": "内置工具 google_serper 不可用",
        "data": {},
    }
