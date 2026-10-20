import json
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessageChunk

from app.http.app import app
from internal.core.tools.builtin_tools import BuiltinProviderManager
from internal.pkg.response import HttpCode, Response, unified_response


def _parse_sse(raw: bytes) -> list[dict]:
    """把 SSE 响应体按空行分帧，解析出每条 data: 的 JSON 事件。"""
    events = []
    for frame in raw.decode("utf-8").split("\n\n"):
        frame = frame.strip()
        if frame.startswith("data: "):
            events.append(json.loads(frame[len("data: "):]))
    return events


class TestUnifiedResponse:
    """统一响应包装：Response 走 JSON，生成器走 SSE。"""

    def test_response_branch_returns_json(self, app_context):
        result = unified_response(Response(code=HttpCode.SUCCESS, data={"a": 1}))
        # json() 返回 (Response 对象, 状态码) 元组
        body, status = result
        assert status == 200
        assert body.get_json()["code"] == HttpCode.SUCCESS.value

    def test_generator_branch_returns_sse(self):
        def gen():
            yield {"event": "agent_message", "data": {"text": "你好"}}
            yield {"event": "agent_action", "data": {"tool": "google_serper"}}

        # SSE 包装依赖请求上下文（stream_with_context）
        with app.test_request_context():
            response = unified_response(gen())
        assert response.mimetype == "text/event-stream"
        assert response.headers["X-Accel-Buffering"] == "no"

    def test_rejects_other_types(self):
        with app.test_request_context():
            with pytest.raises(TypeError):
                unified_response({"not": "allowed"})


def _fake_tools():
    """构造一个假的 google_serper 工具实例，避免真实联网。"""
    tool = MagicMock()
    tool.name = "google_serper"
    tool.invoke.return_value = "杭州今天晴，25 度"
    return tool


class TestDebugStreamOutput:
    """流式测试接口：mock ChatOpenAI 与工具，验证队列/线程/SSE 事件流。"""

    @pytest.fixture(autouse=True)
    def patch_model(self):
        # 工具统一返回假实例，保证走 bind_tools 路径且不依赖真实密钥
        with patch.object(
            BuiltinProviderManager, "get_tool_instance", return_value=_fake_tools()
        ):
            yield

    def test_missing_query_fails(self, client):
        response = client.get("/app/debug_stream?query=")
        body = response.get_json()
        assert body["code"] == HttpCode.FAIL.value

    @patch("internal.handler.app_handler.ChatOpenAI")
    def test_stream_emits_agent_message(self, mock_chat_openai, client):
        # AI 单轮直接回复文本，无工具调用；model.stream 产出的是 AIMessageChunk
        mock_chat_openai.return_value.bind_tools.return_value.stream.return_value = iter(
            [AIMessageChunk("你好"), AIMessageChunk("，我是智能体")]
        )

        response = client.get("/app/debug_stream?app_id=abc&query=你好")

        assert response.content_type.startswith("text/event-stream")
        events = _parse_sse(response.get_data())
        assert events
        assert all(e["event"] == "agent_message" for e in events)
        # 每个事件都补上了 app_id
        assert all(e["app_id"] == "abc" for e in events)
        # token 逐块下发
        assert "".join(e["data"]["text"] for e in events) == "你好，我是智能体"

    @patch("internal.handler.app_handler.ChatOpenAI")
    def test_stream_tool_loop(self, mock_chat_openai, client):
        # 第一轮：AI 决定调用工具（agent_thought），路由到工具节点执行（agent_action）
        tool_call_msg = AIMessageChunk(
            content="",
            tool_calls=[
                {
                    "name": "google_serper",
                    "args": {"query": "杭州天气"},
                    "id": "call_1",
                    "type": "tool_call",
                }
            ],
        )
        # 第二轮：工具结果回填后 AI 给出最终文本（agent_message）
        mock_chat_openai.return_value.bind_tools.return_value.stream.side_effect = [
            iter([tool_call_msg]),
            iter([AIMessageChunk("杭州今天晴，气温 25 度。")]),
        ]

        response = client.get(
            "/app/debug_stream?app_id=abc&query=杭州今天天气怎么样"
        )
        events = _parse_sse(response.get_data())

        types = [e["event"] for e in events]
        assert "agent_thought" in types
        assert "agent_action" in types
        assert "agent_message" in types
        action = next(e for e in events if e["event"] == "agent_action")
        assert action["data"]["tool"] == "google_serper"
        assert "杭州" in action["data"]["observation"]

