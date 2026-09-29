import pytest

from config import Config
from internal.exception import (
    FailException,
    ForbiddenException,
    NoFoundException,
    UnauthorizedException,
    ValidateException,
)
from internal.pkg.response import HttpCode
from internal.server.http import Http


class ErrorRouter:
    def register_router(self, app):
        app.add_url_rule(
            "/custom-error",
            view_func=self.custom_error,
            methods=["GET"],
        )
        app.add_url_rule(
            "/runtime-error",
            view_func=self.runtime_error,
            methods=["GET"],
        )

    @staticmethod
    def custom_error():
        raise NoFoundException("resource not found", {"id": 1})

    @staticmethod
    def runtime_error():
        raise RuntimeError("unexpected error")


def create_app(debug: bool):
    config = Config()
    config.DEBUG = debug
    app = Http(ErrorRouter(), config)
    app.config.update(TESTING=False, PROPAGATE_EXCEPTIONS=debug)
    return app


@pytest.mark.parametrize(
    ("exception_class", "code"),
    [
        (FailException, HttpCode.FAIL),
        (NoFoundException, HttpCode.NOT_FOUND),
        (UnauthorizedException, HttpCode.UNAUTHORIZED),
        (ForbiddenException, HttpCode.FORBIDDEN),
        (ValidateException, HttpCode.VALIDATE_ERROR),
    ],
)
def test_custom_exception_code(exception_class, code):
    error = exception_class("message", {"key": "value"})

    assert error.code == code
    assert error.message == "message"
    assert error.data == {"key": "value"}
    assert str(error) == "message"


def test_custom_exception_handler():
    app = create_app(debug=True)

    response = app.test_client().get("/custom-error")

    assert response.status_code == 200
    assert response.get_json() == {
        "code": HttpCode.NOT_FOUND.value,
        "message": "resource not found",
        "data": {"id": 1},
    }


def test_runtime_exception_handler_in_production():
    app = create_app(debug=False)

    response = app.test_client().get("/runtime-error")

    assert response.status_code == 200
    assert response.get_json() == {
        "code": HttpCode.FAIL.value,
        "message": "unexpected error",
        "data": {},
    }


def test_runtime_exception_is_raised_in_development():
    app = create_app(debug=True)

    with pytest.raises(RuntimeError, match="unexpected error"):
        app.test_client().get("/runtime-error")
