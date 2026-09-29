from dataclasses import dataclass, field
from typing import Any

from flask import jsonify

from internal.pkg.response.http_code import HttpCode


@dataclass
class Response:
    code: HttpCode = HttpCode.SUCCESS
    message: str = ""
    data: Any = field(default_factory=dict)


def json(data: Response = None):
    return jsonify(data), 200


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
