import uuid
from io import BytesIO

import pytest

from internal.entity import DEFAULT_PROCESS_RULE, ProcessType
from internal.pkg.response import HttpCode
from internal.service.document_service import DocumentService


@pytest.fixture
def build_calls(monkeypatch):
    """拦截 trigger_build，避免测试真实提交 Celery 任务污染队列。"""
    calls = []

    # autoparams 包装后真实类在 __wrapped__，patch 必须打在真实类上
    def _fake_trigger(self_service, document_ids):
        calls.extend(document_ids)

    monkeypatch.setattr(DocumentService.__wrapped__, "trigger_build", _fake_trigger)
    return calls


@pytest.fixture(autouse=True)
def _isolate_celery(build_calls):
    """本模块所有用例默认拦截构建任务提交。"""
    return build_calls


@pytest.fixture
def dataset(client, clean_datasets):
    """创建一个知识库用于文档测试。"""
    body = client.post("/datasets", json={"name": "文档测试知识库"}).get_json()
    assert body["code"] == HttpCode.SUCCESS.value
    return body["data"]["dataset"]


@pytest.fixture
def uploaded_files(client, clean_upload_files):
    """上传3个txt文件，返回文件信息列表。"""
    files = []
    for i in range(3):
        data = {"file": (BytesIO(f"content {i}".encode()), f"doc{i}.txt")}
        body = client.post(
            "/upload-files/file",
            data=data,
            content_type="multipart/form-data",
        ).get_json()
        assert body["code"] == HttpCode.SUCCESS.value
        files.append(body["data"])
    return files


def _automatic_payload(file_ids):
    return {
        "upload_file_ids": file_ids,
        "process_type": ProcessType.AUTOMATIC,
    }


def _custom_payload(file_ids, rule=None):
    if rule is None:
        rule = {
            "segment": {
                "separators": ["\n\n", "\n"],
                "chunk_size": 500,
                "chunk_overlap": 50,
            },
            "pre_process_rules": [
                {"id": "remove_extra_space", "enabled": True},
                {"id": "remove_url_and_email", "enabled": False},
            ],
        }
    return {
        "upload_file_ids": file_ids,
        "process_type": ProcessType.CUSTOM,
        "rule": rule,
    }


def test_create_documents_automatic(dataset, uploaded_files, client):
    file_ids = [f["id"] for f in uploaded_files]
    body = client.post(
        f"/datasets/{dataset['id']}/documents",
        json=_automatic_payload(file_ids),
    ).get_json()

    assert body["code"] == HttpCode.SUCCESS.value
    docs = body["data"]["documents"]
    assert len(docs) == 3
    assert body["data"]["batch"]
    # position 从1开始递增
    positions = [d["position"] for d in docs]
    assert positions == sorted(positions)
    assert all(d["status"] == "waiting" for d in docs)
    assert all(d["enabled"] is True for d in docs)


def test_create_documents_custom_rule(dataset, uploaded_files, client):
    file_ids = [f["id"] for f in uploaded_files[:2]]
    body = client.post(
        f"/datasets/{dataset['id']}/documents",
        json=_custom_payload(file_ids),
    ).get_json()

    assert body["code"] == HttpCode.SUCCESS.value
    assert len(body["data"]["documents"]) == 2


def test_create_documents_deduplicates_ids(dataset, uploaded_files, client):
    file_ids = [uploaded_files[0]["id"], uploaded_files[0]["id"]]
    body = client.post(
        f"/datasets/{dataset['id']}/documents",
        json=_automatic_payload(file_ids),
    ).get_json()

    assert body["code"] == HttpCode.SUCCESS.value
    assert len(body["data"]["documents"]) == 1


def test_create_documents_missing_upload_file_ids(dataset, client):
    body = client.post(
        f"/datasets/{dataset['id']}/documents",
        json={"process_type": ProcessType.AUTOMATIC},
    ).get_json()

    assert body["code"] == HttpCode.FAIL.value


def test_create_documents_too_many_files(dataset, client):
    file_ids = [str(uuid.uuid4()) for _ in range(11)]
    body = client.post(
        f"/datasets/{dataset['id']}/documents",
        json=_automatic_payload(file_ids),
    ).get_json()

    assert body["code"] == HttpCode.FAIL.value


def test_create_documents_invalid_process_type(dataset, uploaded_files, client):
    file_ids = [f["id"] for f in uploaded_files[:1]]
    body = client.post(
        f"/datasets/{dataset['id']}/documents",
        json={
            "upload_file_ids": file_ids,
            "process_type": "invalid",
        },
    ).get_json()

    assert body["code"] == HttpCode.VALIDATE_ERROR.value


def test_create_documents_custom_missing_segment(dataset, uploaded_files, client):
    file_ids = [f["id"] for f in uploaded_files[:1]]
    body = client.post(
        f"/datasets/{dataset['id']}/documents",
        json=_custom_payload(file_ids, rule={}),
    ).get_json()

    assert body["code"] == HttpCode.FAIL.value


def test_create_documents_custom_chunk_size_out_of_range(dataset, uploaded_files, client):
    file_ids = [f["id"] for f in uploaded_files[:1]]
    rule = {
        "segment": {
            "separators": ["\n"],
            "chunk_size": 50,
            "chunk_overlap": 10,
        },
        "pre_process_rules": [
            {"id": "remove_extra_space", "enabled": True},
            {"id": "remove_url_and_email", "enabled": True},
        ],
    }
    body = client.post(
        f"/datasets/{dataset['id']}/documents",
        json=_custom_payload(file_ids, rule=rule),
    ).get_json()

    assert body["code"] == HttpCode.FAIL.value


def test_create_documents_custom_overlap_exceeds_half(dataset, uploaded_files, client):
    file_ids = [f["id"] for f in uploaded_files[:1]]
    rule = {
        "segment": {
            "separators": ["\n"],
            "chunk_size": 500,
            "chunk_overlap": 300,
        },
        "pre_process_rules": [
            {"id": "remove_extra_space", "enabled": True},
            {"id": "remove_url_and_email", "enabled": True},
        ],
    }
    body = client.post(
        f"/datasets/{dataset['id']}/documents",
        json=_custom_payload(file_ids, rule=rule),
    ).get_json()

    assert body["code"] == HttpCode.FAIL.value


def test_create_documents_custom_bad_pre_process_rules(dataset, uploaded_files, client):
    file_ids = [f["id"] for f in uploaded_files[:1]]
    rule = {
        "segment": {
            "separators": ["\n"],
            "chunk_size": 500,
            "chunk_overlap": 50,
        },
        "pre_process_rules": [
            {"id": "remove_extra_space", "enabled": True},
        ],
    }
    body = client.post(
        f"/datasets/{dataset['id']}/documents",
        json=_custom_payload(file_ids, rule=rule),
    ).get_json()

    assert body["code"] == HttpCode.FAIL.value


def test_create_documents_dataset_not_found(uploaded_files, client, clean_datasets):
    fake_id = str(uuid.uuid4())
    file_ids = [f["id"] for f in uploaded_files[:1]]
    body = client.post(
        f"/datasets/{fake_id}/documents",
        json=_automatic_payload(file_ids),
    ).get_json()

    assert body["code"] == HttpCode.NOT_FOUND.value


def test_create_documents_triggers_build(dataset, uploaded_files, client, build_calls):
    """创建成功后应立即提交构建任务，文档 ID 与创建结果一致。"""
    file_ids = [f["id"] for f in uploaded_files[:2]]
    body = client.post(
        f"/datasets/{dataset['id']}/documents",
        json=_automatic_payload(file_ids),
    ).get_json()

    assert body["code"] == HttpCode.SUCCESS.value
    docs = body["data"]["documents"]
    assert build_calls == [d["id"] for d in docs]


def test_create_documents_position_increments(dataset, uploaded_files, client):
    file_ids = [f["id"] for f in uploaded_files[:2]]
    # 第一次创建
    client.post(
        f"/datasets/{dataset['id']}/documents",
        json=_automatic_payload(file_ids),
    )
    # 第二次创建，position 应接续
    body = client.post(
        f"/datasets/{dataset['id']}/documents",
        json=_automatic_payload([uploaded_files[2]["id"]]),
    ).get_json()

    assert body["code"] == HttpCode.SUCCESS.value
    doc = body["data"]["documents"][0]
    assert doc["position"] == 3
