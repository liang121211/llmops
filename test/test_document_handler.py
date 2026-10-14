import uuid
from io import BytesIO
from unittest.mock import MagicMock, patch

import inject
import pytest

from internal.model.upload_file import UploadFile
from internal.pkg.response import HttpCode
from internal.service.upload_file_service import UploadFileService


@pytest.fixture
def uploaded_txt_file(client, clean_upload_files):
    """上传一个 txt 文件用于文档加载测试。"""
    data = {"file": (BytesIO(b"hello from upload"), "test.txt")}
    body = client.post(
        "/upload-files/file",
        data=data,
        content_type="multipart/form-data",
    ).get_json()
    assert body["code"] == HttpCode.SUCCESS.value
    return body["data"]


def test_load_document_returns_content(uploaded_txt_file, client):
    file_id = uploaded_txt_file["id"]
    body = client.get(f"/document/{file_id}/load").get_json()

    assert body["code"] == HttpCode.SUCCESS.value
    assert "content" in body["data"]
    assert isinstance(body["data"]["content"], str)


def test_load_document_not_found(client, clean_upload_files):
    fake_id = str(uuid.uuid4())
    body = client.get(f"/document/{fake_id}/load").get_json()

    assert body["code"] == HttpCode.NOT_FOUND.value
