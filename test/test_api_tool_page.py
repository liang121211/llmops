from math import ceil

import inject
import pytest

from internal.model import ApiToolProvider
from internal.pkg.response import HttpCode
from internal.service.api_tool_service import ApiToolService

# TODO: 等待授权认证模块完成后再进行切换调整
ACCOUNT_ID = "a666a888-8888-6666-1234-b9d69212aaaa"

PAGE_URL = "/api-tools"
# 分页列表返回的提供商字段，刻意不包含体积较大的 openapi_schema
PROVIDER_PAGE_KEYS = {
    "id",
    "name",
    "icon",
    "description",
    "headers",
    "tools",
    "created_at",
}
TOOL_KEYS = {
    "id",
    "account_id",
    "provider_id",
    "name",
    "description",
    "url",
    "method",
    "parameters",
    "updated_at",
    "created_at",
}
PAGINATOR_KEYS = {"total_page", "total_record", "current_page", "page_size"}


def account_total(client) -> int:
    """当前账号下的提供商总数，用来推算分页器的期望值。"""
    with client.application.app_context():
        service = inject.instance(ApiToolService)
        return len(service.get_list(ApiToolProvider.account_id == ACCOUNT_ID))


def get_page(client, **params) -> dict:
    body = client.get(PAGE_URL, query_string=params).get_json()
    assert body["code"] == HttpCode.SUCCESS.value, body
    return body["data"]


def test_get_providers_with_page_uses_defaults(client):
    total = account_total(client)

    data = get_page(client)

    assert set(data) == {"list", "paginator"}
    assert set(data["paginator"]) == PAGINATOR_KEYS
    assert data["paginator"]["current_page"] == 1
    assert data["paginator"]["page_size"] == 20
    assert data["paginator"]["total_record"] == total
    assert data["paginator"]["total_page"] == ceil(total / 20)
    assert len(data["list"]) == min(total, 20)


def test_provider_item_contains_expected_fields(client):
    data = get_page(client, current_page=1, page_size=5)

    item = data["list"][0]
    assert set(item) == PROVIDER_PAGE_KEYS
    # 分页列表不返回 openapi 规范原文
    assert "openapi_schema" not in item
    assert item["name"].startswith("分页测试插件")
    assert item["headers"] == [
        {"key": "Authorization", "value": f"Bearer seed-token-{item['name'][-2:]}"}
    ]
    # tools 通过模型上的 property 现查，工具归属于该提供商
    assert len(item["tools"]) == 1
    tool = item["tools"][0]
    assert set(tool) == TOOL_KEYS
    assert tool["provider_id"] == item["id"]
    assert tool["name"].startswith("SeedSuggest")
    assert tool["method"] == "get"


def test_get_providers_with_page_offsets_by_current_page(client):
    first = get_page(client, current_page=1, page_size=5)
    second = get_page(client, current_page=2, page_size=5)

    assert len(first["list"]) == len(second["list"]) == 5
    first_ids = {item["id"] for item in first["list"]}
    second_ids = {item["id"] for item in second["list"]}
    assert first_ids.isdisjoint(second_ids)
    assert second["paginator"]["current_page"] == 2
    assert second["paginator"]["total_page"] == ceil(
        second["paginator"]["total_record"] / 5
    )


def test_search_word_matches_provider_name(client):
    data = get_page(client, search_word="分页测试插件01")

    assert data["paginator"]["total_record"] == 1
    assert [item["name"] for item in data["list"]] == ["分页测试插件01"]


def test_search_word_matches_provider_description(client):
    total = account_total(client)

    data = get_page(client, search_word="字典查询能力")

    # 预置数据的描述里都带这个词，全部命中
    assert data["paginator"]["total_record"] == total
    assert all("字典查询能力" in item["description"] for item in data["list"])


def test_search_word_without_match_returns_empty_page(client):
    data = get_page(client, search_word="一定不存在的提供商")

    assert data["list"] == []
    assert data["paginator"] == {
        "total_page": 0,
        "total_record": 0,
        "current_page": 1,
        "page_size": 20,
    }


def test_current_page_beyond_last_page_returns_empty_list(client):
    total = account_total(client)

    data = get_page(client, current_page=9999, page_size=5)

    assert data["list"] == []
    assert data["paginator"]["total_record"] == total
    assert data["paginator"]["total_page"] == ceil(total / 5)
    assert data["paginator"]["current_page"] == 9999


@pytest.mark.parametrize(
    "params",
    [
        {"current_page": 0},
        {"current_page": 10000},
        {"page_size": 0},
        {"page_size": 101},
        {"current_page": "abc"},
        {"search_word": "长" * 65},
    ],
)
def test_get_providers_with_page_rejects_invalid_params(client, params):
    body = client.get(PAGE_URL, query_string=params).get_json()

    assert body["code"] == HttpCode.VALIDATE_ERROR.value
    assert body["message"]
    assert body["data"] == {}
