import inject
from sqlalchemy import select

from internal.model import ApiTool, ApiToolProvider
from internal.service.api_tool_service import ApiToolService


def test_seed_data_is_ready_for_pagination(app_context, api_tool_seed):
    """预置数据必须通过接口真实落库，供后续分页测试直接使用。"""
    service = inject.instance(ApiToolService)

    # 只增不删：新增与复用的数量之和就是预置总量
    assert api_tool_seed["created"] + api_tool_seed["skipped"] == api_tool_seed["total"]

    providers = service.get_list(
        ApiToolProvider.name.in_(api_tool_seed["names"]),
        order_by=(ApiToolProvider.created_at.asc(),),
    )
    assert len(providers) == api_tool_seed["total"]
    # 同名数据不会重复入库
    assert len({provider.name for provider in providers}) == api_tool_seed["total"]

    tools = list(
        service.db.session.execute(
            select(ApiTool).where(
                ApiTool.provider_id.in_([provider.id for provider in providers])
            )
        ).scalars().all()
    )
    # 每个提供商都解析出一个工具，工具通过 provider_id 关联到提供商
    assert len(tools) == api_tool_seed["total"]
    assert {tool.provider_id for tool in tools} == {
        provider.id for provider in providers
    }
    assert {tool.method for tool in tools} == {"get"}
    assert all(len(tool.parameters) == 2 for tool in tools)
    assert all(provider.header[0]["key"] == "Authorization" for provider in providers)
    assert all(provider.description for provider in providers)


def test_seed_data_is_reusable(app_context, api_tool_seed):
    """重复执行同一份预置名字，账号下只应存在一条同名数据。"""
    service = inject.instance(ApiToolService)

    providers = service.get_list(ApiToolProvider.name == api_tool_seed["names"][0])

    assert len(providers) == 1
