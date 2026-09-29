from typing import Any

from internal.pkg.response import HttpCode


class CustomException(Exception):
    code = HttpCode.FAIL
    message = ""
    data: Any = dict

    def __init__(self, message: str = "", data: Any = None):
        self.code = type(self).code
        self.message = message
        self.data = {} if data is None else data
        super().__init__(message)


class FailException(CustomException):
    pass


class NoFoundException(CustomException):
    code = HttpCode.NOT_FOUND


class UnauthorizedException(CustomException):
    code = HttpCode.UNAUTHORIZED


class ForbiddenException(CustomException):
    code = HttpCode.FORBIDDEN


class ValidateException(CustomException):
    code = HttpCode.VALIDATE_ERROR


__all__ = [
    "CustomException",
    "FailException",
    "NoFoundException",
    "UnauthorizedException",
    "ForbiddenException",
    "ValidateException",
]
