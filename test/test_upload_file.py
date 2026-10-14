import hashlib
from io import BytesIO
from unittest.mock import patch

from sqlalchemy import select

from internal.entity import MAX_UPLOAD_FILE_SIZE
from internal.model import UploadFile
from internal.pkg.response import HttpCode
from pkg.sqlalchemy import db

# 被 patch 的 MinIO 客户端在存储服务模块里，用例不会真的连对象存储
MINIO_PATH = "internal.service.cos_service.Minio"
# TODO: 等待授权认证模块完成后再进行切换调整
ACCOUNT_ID = "a666a888-8888-6666-1234-b9d69212aaaa"
FILE_URL = "/upload-files/file"
IMAGE_URL = "/upload-files/image"
PNG_BYTES = b"\x89PNG\r\n\x1a\nicon-bytes"


def upload(
    client,
    url: str,
    filename: str,
    data: bytes,
    content_type: str | None = None,
) -> dict:
    """发起一次 multipart 上传请求，媒体类型显式指定以免受本机注册表影响。"""
    file_tuple = (BytesIO(data), filename, content_type)
    return client.post(url, data={"file": file_tuple}).get_json()


def uploaded_row(key: str) -> UploadFile | None:
    """按对象存储里的路径查回入库的文件记录。"""
    stmt = select(UploadFile).where(UploadFile.key == key)
    return db.session.execute(stmt).scalars().first()


def key_from_url(image_url: str) -> str:
    """从访问地址里取出 key：最后两段是 <业务类型>/<文件名>。"""
    return "/".join(image_url.rsplit("/", 2)[-2:])


def test_upload_image_returns_only_image_url(client, clean_upload_files):
    with patch(MINIO_PATH):
        body = upload(client, IMAGE_URL, "icon.png", PNG_BYTES, "image/png")

    assert body["code"] == HttpCode.SUCCESS.value, body
    assert set(body["data"]) == {"image_url"}
    image_url = body["data"]["image_url"]
    assert key_from_url(image_url).startswith("image/")
    assert image_url.endswith(".png")


def test_upload_image_saves_file_record(client, clean_upload_files):
    with patch(MINIO_PATH):
        body = upload(client, IMAGE_URL, "icon.png", PNG_BYTES, "image/png")

    upload_file = uploaded_row(key_from_url(body["data"]["image_url"]))
    assert upload_file is not None
    assert str(upload_file.account_id) == ACCOUNT_ID
    assert upload_file.name == "icon.png"
    assert upload_file.extension == "png"
    assert upload_file.mime_type == "image/png"
    assert upload_file.size == len(PNG_BYTES)
    # hash 按文件内容生成，同样的内容 hash 必须一致
    assert upload_file.hash == hashlib.sha256(PNG_BYTES).hexdigest()


def test_upload_image_puts_object_to_storage(client, clean_upload_files):
    with patch(MINIO_PATH) as mock_minio:
        mock_minio.return_value.bucket_exists.return_value = True

        body = upload(client, IMAGE_URL, "icon.png", PNG_BYTES, "image/png")

    args = mock_minio.return_value.put_object.call_args.args
    key = key_from_url(body["data"]["image_url"])
    assert args[1] == key
    assert args[2].getvalue() == PNG_BYTES
    assert args[3] == len(PNG_BYTES)


def test_upload_file_returns_file_info(client, clean_upload_files):
    content = "# 知识库文档".encode()
    with patch(MINIO_PATH):
        body = upload(client, FILE_URL, "手册.MD", content, "text/markdown")

    assert body["code"] == HttpCode.SUCCESS.value, body
    data = body["data"]
    assert set(data) == {
        "id",
        "account_id",
        "name",
        "key",
        "size",
        "extension",
        "mime_type",
        "created_at",
    }
    assert data["account_id"] == ACCOUNT_ID
    assert data["name"] == "手册.MD"
    # 扩展名统一转成小写，key 以业务类型作为目录前缀
    assert data["extension"] == "md"
    assert data["key"].startswith("file/")
    assert data["key"].endswith(".md")
    assert data["size"] == len(content)
    assert data["mime_type"] == "text/markdown"


def test_upload_file_saves_hash_and_record(client, clean_upload_files):
    content = b"title,body\n1,2\n"
    with patch(MINIO_PATH):
        body = upload(client, FILE_URL, "data.csv", content, "text/csv")

    upload_file = uploaded_row(body["data"]["key"])
    assert upload_file is not None
    assert upload_file.hash == hashlib.sha256(content).hexdigest()
    assert upload_file.mime_type == "text/csv"
    assert upload_file.name == "data.csv"


def test_upload_file_accepts_image_extension(client, clean_upload_files):
    with patch(MINIO_PATH):
        body = upload(client, FILE_URL, "banner.jpg", b"jpg-bytes", "image/jpeg")

    assert body["code"] == HttpCode.SUCCESS.value, body
    assert body["data"]["key"].startswith("file/")
    assert body["data"]["extension"] == "jpg"


def test_upload_generates_unique_keys(client, clean_upload_files):
    with patch(MINIO_PATH):
        first = upload(client, FILE_URL, "same.txt", b"same", "text/plain")
        second = upload(client, FILE_URL, "same.txt", b"same", "text/plain")

    assert first["data"]["key"] != second["data"]["key"]
    # 内容相同时 hash 相同，可用于识别重复文件
    first_hash = uploaded_row(first["data"]["key"]).hash
    assert first_hash == uploaded_row(second["data"]["key"]).hash


def test_upload_image_rejects_document(client):
    with patch(MINIO_PATH) as mock_minio:
        body = upload(client, IMAGE_URL, "readme.md", b"# title", "text/markdown")

    assert body["code"] == HttpCode.VALIDATE_ERROR.value
    assert body["message"] == "file参数只支持jpg/jpeg/png/webp/gif/svg格式的文件"
    mock_minio.return_value.put_object.assert_not_called()


def test_upload_file_rejects_unknown_extension(client):
    with patch(MINIO_PATH) as mock_minio:
        body = upload(client, FILE_URL, "virus.exe", b"MZ", "application/octet-stream")

    assert body["code"] == HttpCode.VALIDATE_ERROR.value
    assert body["message"].startswith("file参数只支持txt/markdown/md/pdf")
    mock_minio.return_value.put_object.assert_not_called()


def test_upload_empty_file(client):
    with patch(MINIO_PATH) as mock_minio:
        body = upload(client, FILE_URL, "empty.txt", b"", "text/plain")

    assert body["code"] == HttpCode.VALIDATE_ERROR.value
    assert body["message"] == "file参数上传的文件不能为空"
    mock_minio.return_value.put_object.assert_not_called()


def test_upload_without_file(client):
    body = client.post(FILE_URL, data={}).get_json()

    assert body["code"] == HttpCode.VALIDATE_ERROR.value
    assert body["message"] == "file参数必须上传文件"


def test_upload_oversize_file(client):
    oversize = b"a" * (MAX_UPLOAD_FILE_SIZE + 1)

    with patch(MINIO_PATH) as mock_minio:
        body = upload(client, FILE_URL, "big.txt", oversize, "text/plain")

    assert body["code"] == HttpCode.VALIDATE_ERROR.value
    assert body["message"] == "file参数大小不能超过16MB"
    mock_minio.return_value.put_object.assert_not_called()


def test_upload_max_size_file_is_allowed(client, clean_upload_files):
    largest = b"a" * MAX_UPLOAD_FILE_SIZE

    with patch(MINIO_PATH):
        body = upload(client, FILE_URL, "largest.txt", largest, "text/plain")

    assert body["code"] == HttpCode.SUCCESS.value, body
    assert body["data"]["size"] == MAX_UPLOAD_FILE_SIZE
