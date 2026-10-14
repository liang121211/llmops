import pytest
from flask import Flask
from werkzeug.datastructures import MultiDict

from internal.schema.app_schema import CompletionReq, PingForm

REQUIRED_MESSAGE = "query参数必须传递"
MAX_LENGTH_MESSAGE = "query参数最大长度为2000字符"


@pytest.fixture
def request_context():
    app = Flask("schema_test")
    # 与生产配置保持一致：API 场景不启用 CSRF 令牌校验
    app.config.update(WTF_CSRF_ENABLED=False, SECRET_KEY="test-secret-key")
    with app.test_request_context():
        yield


def build_form(payload):
    return CompletionReq(formdata=MultiDict(payload))


def test_completion_req_accepts_query(request_context):
    form = build_form({"query": "你好"})

    assert form.validate() is True
    assert form.query.data == "你好"
    assert form.errors == {}


@pytest.mark.parametrize(
    ("payload", "expected_message"),
    [
        ({}, REQUIRED_MESSAGE),
        ({"query": ""}, REQUIRED_MESSAGE),
        ({"query": "   "}, REQUIRED_MESSAGE),
    ],
)
def test_completion_req_requires_query(request_context, payload, expected_message):
    form = build_form(payload)

    assert form.validate() is False
    assert form.errors == {"query": [expected_message]}


def test_completion_req_allows_maximum_length(request_context):
    form = build_form({"query": "a" * 2000})

    assert form.validate() is True


def test_completion_req_rejects_over_maximum_length(request_context):
    form = build_form({"query": "a" * 2001})

    assert form.validate() is False
    assert form.errors == {"query": [MAX_LENGTH_MESSAGE]}


def test_completion_req_ignores_unknown_fields(request_context):
    form = build_form({"query": "你好", "unexpected": "x"})

    assert form.validate() is True
    assert not hasattr(form, "unexpected")


def test_ping_form_token_is_optional(request_context):
    form = PingForm(formdata=MultiDict({}))

    assert form.validate() is True
