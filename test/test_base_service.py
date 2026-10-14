import uuid

import inject
import pytest

from internal.model import App
from internal.service.api_tool_service import ApiToolService
from internal.service.app_service import AppService
from internal.service.base_service import BaseService


@pytest.fixture
def service(app_context):
    """AppService 就是一个具体的 BaseService，用它来验证通用增删改查。"""
    return inject.instance(AppService)


@pytest.fixture
def created_apps(service):
    """准备两条应用数据，用例结束后按主键清理。"""
    created = [
        service.create(
            account_id=uuid.uuid4(),
            name="基类测试应用A",
            icon="a.png",
            config={"temperature": 0.1},
        ),
        service.create(
            account_id=uuid.uuid4(),
            name="基类测试应用B",
            icon="b.png",
            config={"temperature": 0.2},
        ),
    ]
    yield created
    for app in created:
        service.delete(app.id)


def test_services_inherit_base_service(service):
    # 子类只需要声明 model，通用方法全部来自基类
    assert isinstance(service, BaseService)
    assert service.model is App
    assert isinstance(inject.instance(ApiToolService), BaseService)


def test_get_by_id_returns_created_row(service, created_apps):
    app = service.get_by_id(created_apps[0].id)

    assert app.name == "基类测试应用A"
    assert service.get_by_id(uuid.uuid4()) is None


def test_get_list_filters_and_orders(service, created_apps):
    matched = service.get_list(App.name == "基类测试应用A")
    assert [app.name for app in matched] == ["基类测试应用A"]

    ordered = service.get_list(
        App.name.like("基类测试应用%"), order_by=(App.name.desc(),)
    )
    assert [app.name for app in ordered] == ["基类测试应用B", "基类测试应用A"]


def test_get_first_and_exists(service, created_apps):
    first = service.get_first(App.name.like("基类测试应用%"), order_by=(App.name.asc(),))
    assert first.name == "基类测试应用A"

    assert service.exists(App.name == "基类测试应用B") is True
    assert service.exists(App.name == "不存在的应用") is False
    assert service.get_first(App.name == "不存在的应用") is None


def test_update_only_overrides_given_fields(service, created_apps):
    app_id = created_apps[0].id

    updated = service.update(app_id, name="基类测试应用A-已改名")

    assert updated.name == "基类测试应用A-已改名"
    # 没有传入的字段保持原值
    assert updated.icon == "a.png"
    assert updated.config == {"temperature": 0.1}
    assert service.update(uuid.uuid4(), name="任意名字") is None


def test_delete_removes_row_and_reports_result(service, created_apps):
    app_id = created_apps[1].id

    assert service.delete(app_id) is True
    assert service.get_by_id(app_id) is None
    assert service.delete(app_id) is False


def test_create_copies_mutable_values(service):
    config = {"temperature": 0.5}

    app = service.create(
        account_id=uuid.uuid4(), name="复制测试应用", icon="c.png", config=config
    )
    # 外部字典后续变化不应影响已经入库的数据
    config["temperature"] = 0.9
    stored = service.get_by_id(app.id)

    assert stored.config == {"temperature": 0.5}
    service.delete(app.id)
