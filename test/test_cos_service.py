from io import BytesIO
from unittest.mock import MagicMock, patch

import inject
import pytest

from internal.entity import StorageType
from internal.exception import FailException
from internal.service.cos_service import CosService

# 被 patch 的驱动客户端都在服务模块里，测试不会真的连对象存储
MINIO_PATH = "internal.service.cos_service.Minio"
COS_CLIENT_PATH = "internal.service.cos_service.CosS3Client"
KEY = "image/0f1e2d3c.png"


@pytest.fixture
def cos_service():
    """容器里的对象存储服务，配置项在用例里覆盖后由 monkeypatch 还原。"""
    return inject.instance(CosService)


@pytest.fixture
def minio_driver(cos_service, monkeypatch):
    """切到本地 MinIO 驱动。"""
    monkeypatch.setattr(cos_service.config, "STORAGE_TYPE", StorageType.MINIO)
    monkeypatch.setattr(cos_service.config, "MINIO_SECURE", False)
    return cos_service


@pytest.fixture
def cos_driver(cos_service, monkeypatch):
    """切到腾讯云 COS 驱动，并补齐必要的配置项。"""
    monkeypatch.setattr(cos_service.config, "STORAGE_TYPE", StorageType.COS)
    monkeypatch.setattr(cos_service.config, "COS_SECRET_ID", "test-secret-id")
    monkeypatch.setattr(cos_service.config, "COS_SECRET_KEY", "test-secret-key")
    monkeypatch.setattr(cos_service.config, "COS_BUCKET", "test-bucket")
    monkeypatch.setattr(cos_service.config, "COS_REGION", "ap-guangzhou")
    monkeypatch.setattr(cos_service.config, "COS_SCHEME", "https")
    monkeypatch.setattr(cos_service.config, "COS_DOMAIN", "")
    return cos_service


def test_default_storage_type_is_minio(cos_service):
    # .env 里 FLASK_ENV=development，默认走本地 MinIO
    assert cos_service.storage_type == StorageType.MINIO


def test_storage_type_rejects_unknown_driver(cos_service, monkeypatch):
    monkeypatch.setattr(cos_service.config, "STORAGE_TYPE", "oss")

    with pytest.raises(FailException) as error:
        cos_service.get_file_url(KEY)

    assert "不支持的对象存储驱动：oss" in str(error.value)


def test_minio_upload_creates_missing_bucket(minio_driver):
    with patch(MINIO_PATH) as mock_minio:
        client = mock_minio.return_value
        client.bucket_exists.return_value = False

        minio_driver.upload_file(KEY, BytesIO(b"icon"))

    bucket = minio_driver.config.MINIO_BUCKET
    client.bucket_exists.assert_called_once_with(bucket)
    client.make_bucket.assert_called_once_with(bucket)


def test_minio_upload_skips_existing_bucket(minio_driver):
    with patch(MINIO_PATH) as mock_minio:
        client = mock_minio.return_value
        client.bucket_exists.return_value = True

        minio_driver.upload_file(KEY, BytesIO(b"icon"))

    client.make_bucket.assert_not_called()


def test_minio_upload_puts_object_with_length(minio_driver):
    with patch(MINIO_PATH) as mock_minio:
        mock_minio.return_value.bucket_exists.return_value = True

        minio_driver.upload_file(KEY, BytesIO(b"icon-bytes"))

    args = mock_minio.return_value.put_object.call_args.args
    assert args[0] == minio_driver.config.MINIO_BUCKET
    assert args[1] == KEY
    # 上传的内容与长度必须一致，否则 MinIO 会报长度不匹配
    assert args[2].getvalue() == b"icon-bytes"
    assert args[3] == len(b"icon-bytes")


def test_minio_client_uses_config(minio_driver):
    config = minio_driver.config

    with patch(MINIO_PATH) as mock_minio:
        mock_minio.return_value.bucket_exists.return_value = True

        minio_driver.upload_file(KEY, BytesIO(b"icon"))

    assert mock_minio.call_args.kwargs == {
        "endpoint": config.MINIO_ENDPOINT,
        "access_key": config.MINIO_ACCESS_KEY,
        "secret_key": config.MINIO_SECRET_KEY,
        "secure": config.MINIO_SECURE,
    }


def test_minio_download_returns_bytes_and_releases_connection(minio_driver):
    response = MagicMock()
    response.read.return_value = b"file-content"
    with patch(MINIO_PATH) as mock_minio:
        client = mock_minio.return_value
        client.get_object.return_value = response

        data = minio_driver.download_file(KEY)

    assert data == b"file-content"
    client.get_object.assert_called_once_with(
        minio_driver.config.MINIO_BUCKET, KEY
    )
    # 连接没有归还会耗尽 urllib3 的连接池
    response.close.assert_called_once_with()
    response.release_conn.assert_called_once_with()


def test_minio_file_url(minio_driver):
    config = minio_driver.config

    url = minio_driver.get_file_url(KEY)

    assert url == f"http://{config.MINIO_ENDPOINT}/{config.MINIO_BUCKET}/{KEY}"


def test_minio_file_url_with_secure(minio_driver, monkeypatch):
    monkeypatch.setattr(minio_driver.config, "MINIO_SECURE", True)

    url = minio_driver.get_file_url(KEY)

    assert url.startswith("https://")


def test_cos_upload_uses_put_object(cos_driver):
    with patch(COS_CLIENT_PATH) as mock_client_cls:
        cos_driver.upload_file(KEY, BytesIO(b"icon-bytes"))

    assert mock_client_cls.return_value.put_object.call_args.kwargs == {
        "Bucket": "test-bucket",
        "Key": KEY,
        "Body": b"icon-bytes",
    }


def test_cos_download_reads_body(cos_driver):
    with patch(COS_CLIENT_PATH) as mock_client_cls:
        client = mock_client_cls.return_value
        client.get_object.return_value["Body"].read.return_value = b"cos-content"

        data = cos_driver.download_file(KEY)

    assert data == b"cos-content"
    assert client.get_object.call_args.kwargs == {
        "Bucket": "test-bucket",
        "Key": KEY,
    }


def test_cos_file_url_uses_bucket_domain(cos_driver):
    url = cos_driver.get_file_url(KEY)

    assert url == f"https://test-bucket.cos.ap-guangzhou.myqcloud.com/{KEY}"


def test_cos_file_url_prefers_custom_domain(cos_driver, monkeypatch):
    monkeypatch.setattr(cos_driver.config, "COS_DOMAIN", "https://cdn.example.com/")

    url = cos_driver.get_file_url(KEY)

    assert url == f"https://cdn.example.com/{KEY}"


def test_cos_missing_config_raises(cos_service, monkeypatch):
    monkeypatch.setattr(cos_service.config, "STORAGE_TYPE", StorageType.COS)
    monkeypatch.setattr(cos_service.config, "COS_SECRET_ID", "")

    with pytest.raises(FailException) as error:
        cos_service.upload_file(KEY, BytesIO(b"icon"))

    assert "腾讯云COS配置不完整" in str(error.value)
