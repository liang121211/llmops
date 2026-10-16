from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from internal.extension.celery_extension import FlaskTask
from internal.pkg.response import HttpCode
from internal.task.build_documents_task import build_documents_task


DEMO_TASK_URL = "/celery/demo_task"


@pytest.fixture
def mock_demo_task():
    """patch demo_task.delay 避免真的往 broker 发消息。"""
    with patch("internal.service.celery_service.demo_task") as mock:
        async_result = MagicMock()
        async_result.id = "test-task-id-12345"
        mock.delay.return_value = async_result
        yield mock


def test_create_demo_task_returns_task_id(client, mock_demo_task):
    body = client.post(DEMO_TASK_URL, json={"seconds": 3}).get_json()

    assert body["code"] == HttpCode.SUCCESS.value, body
    assert body["data"]["task_id"] == "test-task-id-12345"
    mock_demo_task.delay.assert_called_once_with(3)


def test_create_demo_task_uses_default_seconds(client, mock_demo_task):
    body = client.post(DEMO_TASK_URL, json={}).get_json()

    assert body["code"] == HttpCode.SUCCESS.value, body
    # seconds 默认值为 5
    mock_demo_task.delay.assert_called_once_with(5)


def test_create_demo_task_rejects_invalid_seconds(client, mock_demo_task):
    body = client.post(DEMO_TASK_URL, json={"seconds": 0}).get_json()

    assert body["code"] == HttpCode.VALIDATE_ERROR.value
    mock_demo_task.delay.assert_not_called()


def test_create_demo_task_rejects_oversize_seconds(client, mock_demo_task):
    body = client.post(DEMO_TASK_URL, json={"seconds": 61}).get_json()

    assert body["code"] == HttpCode.VALIDATE_ERROR.value
    mock_demo_task.delay.assert_not_called()


@patch("internal.service.celery_service.AsyncResult")
def test_get_demo_task_pending(mock_async_result_cls, client):
    instance = mock_async_result_cls.return_value
    instance.state = "PENDING"
    instance.result = None

    body = client.get(f"{DEMO_TASK_URL}?task_id=abc-123").get_json()

    assert body["code"] == HttpCode.SUCCESS.value
    assert body["data"] == {"state": "PENDING", "result": None}


@patch("internal.service.celery_service.AsyncResult")
def test_get_demo_task_success(mock_async_result_cls, client):
    instance = mock_async_result_cls.return_value
    instance.state = "SUCCESS"
    instance.result = "demo_task completed after 5s"

    body = client.get(f"{DEMO_TASK_URL}?task_id=abc-123").get_json()

    assert body["code"] == HttpCode.SUCCESS.value
    assert body["data"] == {
        "state": "SUCCESS",
        "result": "demo_task completed after 5s",
    }


@patch("internal.service.celery_service.AsyncResult")
def test_get_demo_task_failure(mock_async_result_cls, client):
    instance = mock_async_result_cls.return_value
    instance.state = "FAILURE"
    instance.result = RuntimeError("something broke")

    body = client.get(f"{DEMO_TASK_URL}?task_id=abc-123").get_json()

    assert body["code"] == HttpCode.SUCCESS.value
    assert body["data"]["state"] == "FAILURE"
    assert "something broke" in body["data"]["result"]


def test_get_demo_task_requires_task_id(client):
    body = client.get(DEMO_TASK_URL).get_json()

    assert body["code"] == HttpCode.VALIDATE_ERROR.value
    assert "task_id" in body["message"]


class TestFlaskTaskBase:
    """装饰器任务必须继承 FlaskTask，否则 worker 里访问 db.session 会报无应用上下文。"""

    def test_build_documents_task_uses_flask_task_base(self):
        assert isinstance(build_documents_task, FlaskTask)

    def test_task_runs_with_app_context(self):
        # 用不存在的文档 id：任务体会正常走到 db.session.get 并跳过，无副作用
        result = build_documents_task.apply(args=[[str(uuid4())]])

        assert result.successful(), result.result
        assert result.result == "built 1 documents"
