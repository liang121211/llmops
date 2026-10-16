import uuid

import pytest

from internal.pkg.response import HttpCode
from internal.service.dataset_service import (
    DEFAULT_DATASET_DESCRIPTION_FORMATTER,
    DatasetService,
)


@pytest.fixture
def created_dataset(client, clean_datasets):
    """创建一条知识库数据，测试结束后由 clean_datasets 清理。"""
    body = client.post("/datasets", json={"name": "测试知识库"}).get_json()
    assert body["code"] == HttpCode.SUCCESS.value
    return body["data"]["dataset"]


def test_create_dataset_with_required_fields(created_dataset):
    assert uuid.UUID(created_dataset["id"])
    assert created_dataset["name"] == "测试知识库"
    assert created_dataset["description"] == DEFAULT_DATASET_DESCRIPTION_FORMATTER.format(
        name="测试知识库"
    )
    assert created_dataset["icon"] == ""
    assert created_dataset["related_app_count"] == 0
    assert created_dataset["document_count"] == 0
    assert created_dataset["character_count"] == 0
    assert created_dataset["created_at"]
    assert created_dataset["updated_at"]


def test_create_dataset_with_all_fields(client, clean_datasets):
    body = client.post(
        "/datasets",
        json={
            "name": "完整知识库",
            "icon": "https://example.com/icon.png",
            "description": "自定义描述内容",
        },
    ).get_json()

    assert body["code"] == HttpCode.SUCCESS.value
    dataset = body["data"]["dataset"]
    assert dataset["name"] == "完整知识库"
    assert dataset["icon"] == "https://example.com/icon.png"
    assert dataset["description"] == "自定义描述内容"


def test_create_dataset_duplicate_name_fails(client, created_dataset):
    body = client.post("/datasets", json={"name": "测试知识库"}).get_json()

    assert body["code"] == HttpCode.FAIL.value
    assert "已存在" in body["message"]


def test_create_dataset_missing_name_fails(client, clean_datasets):
    body = client.post("/datasets", json={}).get_json()

    assert body["code"] == HttpCode.VALIDATE_ERROR.value


def test_create_dataset_name_too_long_fails(client, clean_datasets):
    body = client.post("/datasets", json={"name": "x" * 257}).get_json()

    assert body["code"] == HttpCode.VALIDATE_ERROR.value


def test_get_dataset_returns_detail(created_dataset, client):
    dataset_id = created_dataset["id"]
    body = client.get(f"/datasets/{dataset_id}").get_json()

    assert body["code"] == HttpCode.SUCCESS.value
    assert body["data"]["dataset"]["id"] == dataset_id
    assert body["data"]["dataset"]["name"] == "测试知识库"


def test_get_dataset_not_found(client, clean_datasets):
    fake_id = str(uuid.uuid4())
    body = client.get(f"/datasets/{fake_id}").get_json()

    assert body["code"] == HttpCode.NOT_FOUND.value


def test_update_dataset_modifies_fields(created_dataset, client):
    dataset_id = created_dataset["id"]
    body = client.put(
        f"/datasets/{dataset_id}",
        json={"name": "更新后的知识库", "icon": "https://new-icon.png"},
    ).get_json()

    assert body["code"] == HttpCode.SUCCESS.value
    dataset = body["data"]["dataset"]
    assert dataset["name"] == "更新后的知识库"
    assert dataset["icon"] == "https://new-icon.png"
    # description 未传应保持原值
    assert dataset["description"] == DEFAULT_DATASET_DESCRIPTION_FORMATTER.format(
        name="测试知识库"
    )
    assert dataset["updated_at"] >= created_dataset["updated_at"]


def test_update_dataset_partial_fields(created_dataset, client):
    dataset_id = created_dataset["id"]
    body = client.put(
        f"/datasets/{dataset_id}",
        json={"description": "只改描述"},
    ).get_json()

    assert body["code"] == HttpCode.SUCCESS.value
    dataset = body["data"]["dataset"]
    assert dataset["description"] == "只改描述"
    assert dataset["name"] == "测试知识库"


def test_update_dataset_duplicate_name_fails(client, clean_datasets):
    client.post("/datasets", json={"name": "知识库A"})
    body_b = client.post("/datasets", json={"name": "知识库B"}).get_json()
    dataset_b_id = body_b["data"]["dataset"]["id"]

    body = client.put(
        f"/datasets/{dataset_b_id}",
        json={"name": "知识库A"},
    ).get_json()

    assert body["code"] == HttpCode.FAIL.value
    assert "已存在" in body["message"]


def test_update_dataset_not_found(client, clean_datasets):
    fake_id = str(uuid.uuid4())
    body = client.put(
        f"/datasets/{fake_id}",
        json={"name": "不存在的知识库"},
    ).get_json()

    assert body["code"] == HttpCode.NOT_FOUND.value


def test_delete_dataset_submits_async_task(created_dataset, client, monkeypatch):
    """删除已改为异步任务：接口只提交任务，知识库行等任务执行时才清理。"""
    submitted = []

    # autoparams 包装后真实类在 __wrapped__，patch 必须打在真实类上
    def _fake_trigger(self_service, dataset_id):
        submitted.append(str(dataset_id))

    monkeypatch.setattr(DatasetService.__wrapped__, "trigger_delete", _fake_trigger)

    dataset_id = created_dataset["id"]
    body = client.delete(f"/datasets/{dataset_id}").get_json()

    assert body["code"] == HttpCode.SUCCESS.value
    assert body["data"]["id"] == dataset_id
    assert submitted == [dataset_id]

    # 任务尚未执行，知识库记录仍然存在
    get_body = client.get(f"/datasets/{dataset_id}").get_json()
    assert get_body["code"] == HttpCode.SUCCESS.value


def test_delete_dataset_not_found(client, clean_datasets):
    fake_id = str(uuid.uuid4())
    body = client.delete(f"/datasets/{fake_id}").get_json()

    assert body["code"] == HttpCode.NOT_FOUND.value


def test_get_datasets_pagination(client, clean_datasets):
    for i in range(3):
        client.post("/datasets", json={"name": f"分页知识库{i}"})

    body = client.get("/datasets?current_page=1&page_size=2").get_json()

    assert body["code"] == HttpCode.SUCCESS.value
    assert len(body["data"]["datasets"]) == 2
    assert body["data"]["paginator"]["total_record"] >= 3
    assert body["data"]["paginator"]["page_size"] == 2
    assert body["data"]["paginator"]["current_page"] == 1


def test_get_datasets_default_pagination(client, clean_datasets):
    client.post("/datasets", json={"name": "默认分页知识库"})

    body = client.get("/datasets").get_json()

    assert body["code"] == HttpCode.SUCCESS.value
    assert "datasets" in body["data"]
    assert "paginator" in body["data"]
    assert body["data"]["paginator"]["current_page"] == 1
    assert body["data"]["paginator"]["page_size"] == 20
