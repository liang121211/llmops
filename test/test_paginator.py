from math import ceil

import pytest
from marshmallow import Schema, fields
from sqlalchemy import func, select
from werkzeug.datastructures import MultiDict

from app.http.app import app
from internal.model import ApiToolProvider
from pkg.paginator import DEFAULT_PAGE_SIZE, PageModel, Paginator, PaginatorReq
from pkg.sqlalchemy import db

# TODO: 等待授权认证模块完成后再进行切换调整
ACCOUNT_ID = "a666a888-8888-6666-1234-b9d69212aaaa"


class _ProviderName(Schema):
    """只取名字的最小 schema，用来验证 dump 的裁剪能力。"""

    name = fields.String()


def build_req(**params) -> PaginatorReq:
    """按控制层同样的方式构造分页请求表单并执行校验。"""
    with app.test_request_context():
        formdata = MultiDict([(key, str(value)) for key, value in params.items()])
        form = PaginatorReq(formdata=formdata)
        form.validate()
        return form


def provider_stmt():
    """预置的分页测试数据，只读查询，用例不会修改它。"""
    return (
        select(ApiToolProvider)
        .where(ApiToolProvider.account_id == ACCOUNT_ID)
        .order_by(ApiToolProvider.created_at.desc(), ApiToolProvider.id.desc())
    )


def total_providers() -> int:
    stmt = select(func.count()).select_from(ApiToolProvider).where(
        ApiToolProvider.account_id == ACCOUNT_ID
    )
    return db.session.execute(stmt).scalar() or 0


def test_paginator_req_uses_defaults(app_context):
    req = build_req()

    assert req.errors == {}
    assert req.current_page.data == 1
    assert req.page_size.data == DEFAULT_PAGE_SIZE


def test_paginator_req_accepts_values_in_range(app_context):
    req = build_req(current_page=9999, page_size=100)

    assert req.errors == {}
    assert req.current_page.data == 9999
    assert req.page_size.data == 100


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"current_page": 0}, "current_page"),
        ({"current_page": 10000}, "current_page"),
        ({"page_size": 0}, "page_size"),
        ({"page_size": 101}, "page_size"),
        ({"current_page": "abc"}, "current_page"),
    ],
)
def test_paginator_req_rejects_invalid_values(app_context, params, field):
    with app.test_request_context():
        formdata = MultiDict([(key, str(value)) for key, value in params.items()])
        req = PaginatorReq(formdata=formdata)

        assert req.validate() is False

    assert field in req.errors


def test_paginator_req_reports_non_integer_in_chinese(app_context):
    req = build_req(page_size="五")

    assert req.errors["page_size"] == [
        "page_size参数必须是整数",
        "page_size参数的取值范围为1-100",
    ]


def test_paginate_returns_first_page(app_context):
    total = total_providers()

    page = Paginator.paginate(provider_stmt(), build_req(current_page=1, page_size=5))

    assert isinstance(page, PageModel)
    assert len(page.list) == min(total, 5)
    assert page.paginator.total_record == total
    assert page.paginator.current_page == 1
    assert page.paginator.page_size == 5
    assert page.paginator.total_page == ceil(total / 5)


def test_paginate_offsets_by_current_page(app_context):
    first = Paginator.paginate(provider_stmt(), build_req(current_page=1, page_size=5))
    second = Paginator.paginate(provider_stmt(), build_req(current_page=2, page_size=5))

    first_ids = [item.id for item in first.list]
    second_ids = [item.id for item in second.list]
    assert len(first_ids) == len(second_ids) == 5
    assert set(first_ids).isdisjoint(second_ids)
    # 两页看到的是同一份数据规模
    assert first.paginator.total_record == second.paginator.total_record


def test_paginate_beyond_last_page_returns_empty_list(app_context):
    page = Paginator.paginate(provider_stmt(), build_req(current_page=9999, page_size=5))

    assert page.list == []
    assert page.paginator.total_record == total_providers()
    assert page.paginator.total_page == ceil(total_providers() / 5)


def test_paginate_on_empty_result(app_context):
    stmt = select(ApiToolProvider).where(ApiToolProvider.name == "一定不存在的提供商")

    page = Paginator.paginate(stmt, build_req())

    assert page.list == []
    assert page.paginator.total_record == 0
    assert page.paginator.total_page == 0


def test_page_model_dump_without_schema(app_context):
    page = Paginator.paginate(provider_stmt(), build_req(page_size=2))

    dumped = page.dump()

    assert set(dumped) == {"list", "paginator"}
    # 不传 schema 时原样返回模型实例
    assert dumped["list"] == page.list
    assert set(dumped["paginator"]) == {
        "total_page",
        "total_record",
        "current_page",
        "page_size",
    }


def test_page_model_dump_with_schema(app_context):
    page = Paginator.paginate(provider_stmt(), build_req(page_size=2))

    dumped = page.dump(_ProviderName())

    assert dumped["list"] == [{"name": item.name} for item in page.list]
