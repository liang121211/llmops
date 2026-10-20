import json as json_lib
from collections.abc import Generator
from dataclasses import dataclass, field
from typing import Any

from flask import Response as FlaskResponse
from flask import jsonify, stream_with_context

from internal.pkg.response.http_code import HttpCode


@dataclass
class Response:
    code: HttpCode = HttpCode.SUCCESS
    message: str = ""
    data: Any = field(default_factory=dict)


def json(data: Response = None):
    return jsonify(data), 200


def _sse_frame(item: Any) -> str:
    """把一条流式事件序列化成 SSE 数据帧。"""
    payload = item if isinstance(item, str) else json_lib.dumps(
        item, ensure_ascii=False, default=str
    )
    return f"data: {payload}\n\n"


def stream_response(generator: Generator) -> FlaskResponse:
    """把生成器包装成 SSE 流式响应，逐条事件以 data: 帧输出。

    用 stream_with_context 保住请求上下文，让生成器在消费阶段仍可访问
    Flask app/request；关闭缓冲以便事件实时下发。
    """

    def event_stream():
        for item in generator:
            yield _sse_frame(item)

    response = FlaskResponse(
        stream_with_context(event_stream()), mimetype="text/event-stream"
    )
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    response.headers["Connection"] = "keep-alive"
    return response


def unified_response(result: Response | Generator):
    """统一响应出口：Response 走 JSON 块输出，生成器走 SSE 流式输出。"""
    if isinstance(result, Response):
        return json(result)
    if isinstance(result, Generator):
        return stream_response(result)
    raise TypeError("unified_response 只接受 Response 或 Generator")


def success_json(data: Any = None):
    return json(Response(code=HttpCode.SUCCESS, message="", data=data))


def fail_json(data: Any = None):
    return json(Response(code=HttpCode.FAIL, message="", data=data))


def validate_error_json(error: dict):
    first_key = next(iter(error), "")
    first_error = error.get(first_key, "") if first_key else ""
    if isinstance(first_error, (list, tuple)):
        first_error = first_error[0] if first_error else ""
    return json(
        Response(code=HttpCode.VALIDATE_ERROR, message=str(first_error))
    )


def message(code: HttpCode = None, msg: str = ""):
    return json(Response(code=code, message=msg, data={}))


def success_message(message: str = ""):
    return globals()["message"](HttpCode.SUCCESS, message)


def fail_message(message: str = ""):
    return globals()["message"](HttpCode.FAIL, message)


def not_found_message(message: str = ""):
    return globals()["message"](HttpCode.NOT_FOUND, message)


def unauthorized_message(message: str = ""):
    return globals()["message"](HttpCode.UNAUTHORIZED, message)


def forbidden_message(message: str = ""):
    return globals()["message"](HttpCode.FORBIDDEN, message)


__all__ = [
    "Response",
    "json",
    "stream_response",
    "unified_response",
    "success_json",
    "fail_json",
    "validate_error_json",
    "message",
    "success_message",
    "fail_message",
    "not_found_message",
    "unauthorized_message",
    "forbidden_message",
]
