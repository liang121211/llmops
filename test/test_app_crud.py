import uuid

import inject
import pytest

from internal.handler.app_handler import (
    APP_CONFIG,
    APP_ICON,
    APP_NAME,
    UPDATED_APP_CONFIG,
    UPDATED_APP_NAME,
)
from internal.pkg.response import HttpCode
from internal.service.app_service import AppService


def _create_app(client):
    """调用新增接口创建一条应用数据，返回响应中的应用详情。"""
    body = client.post("/app").get_json()
    assert body["code"] == HttpCode.SUCCESS.value
    return body["data"]["app"]


@pytest.fixture
def created_app(client):
    """准备一条应用数据，测试结束后删除，保证数据库干净。"""
    app = _create_app(client)
    yield app
    # 按主键精确清理本条数据，不使用 DELETE 接口以免误删其它应用
    with client.application.app_context():
        inject.instance(AppService).delete(uuid.UUID(app["id"]))


def test_create_app_uses_server_side_defaults(created_app):
    # 新增接口不接收参数，应用内容全部来自服务端常量
    assert uuid.UUID(created_app["id"])
    assert uuid.UUID(created_app["account_id"])
    assert created_app["name"] == APP_NAME
    assert created_app["icon"] == APP_ICON
    assert created_app["config"] == APP_CONFIG
    assert created_app["created_at"]
    assert created_app["updated_at"]


def test_get_apps_lists_created_app(created_app, client):
    body = client.get("/app").get_json()

    assert body["code"] == HttpCode.SUCCESS.value
    assert created_app["id"] in [item["id"] for item in body["data"]["apps"]]


def test_update_app_modifies_latest_app(created_app, client):
    body = client.put("/app").get_json()

    assert body["code"] == HttpCode.SUCCESS.value
    assert body["data"]["app"]["id"] == created_app["id"]
    assert body["data"]["app"]["name"] == UPDATED_APP_NAME
    assert body["data"]["app"]["config"] == UPDATED_APP_CONFIG
    # 修改时间应当被 onupdate 刷新
    assert body["data"]["app"]["updated_at"] >= created_app["updated_at"]


def test_delete_app_removes_latest_app(created_app, client):
    body = client.delete("/app").get_json()

    assert body["code"] == HttpCode.SUCCESS.value
    assert body["data"]["id"] == created_app["id"]

    apps = client.get("/app").get_json()["data"]["apps"]
    assert created_app["id"] not in [item["id"] for item in apps]
