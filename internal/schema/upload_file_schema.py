from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired, FileSize
from marshmallow import Schema, fields
from werkzeug.datastructures import FileStorage
from wtforms import ValidationError

from internal.entity import (
    ALLOWED_DOCUMENT_EXTENSION,
    ALLOWED_IMAGE_EXTENSION,
    MAX_UPLOAD_FILE_SIZE,
)

# 通用文件上传允许的扩展名：文档加图片
ALLOWED_FILE_EXTENSION = ALLOWED_DOCUMENT_EXTENSION + ALLOWED_IMAGE_EXTENSION


class _FileNotEmpty:
    """空文件校验，FileRequired 只判断有没有选文件，0 字节的文件同样要拦住。"""

    def __call__(self, form, field):
        file_storage = field.data
        # 没有上传文件时交给 FileRequired 报错
        if not isinstance(file_storage, FileStorage) or not file_storage:
            return
        file_storage.stream.seek(0, 2)
        size = file_storage.stream.tell()
        # 读完大小要把流放回开头，后面的校验与保存才能拿到完整内容
        file_storage.stream.seek(0)
        if size == 0:
            raise ValidationError(f"{field.name}参数上传的文件不能为空")


def _validators(extensions: list[str]) -> list:
    """按允许的扩展名拼装文件校验器，图片上传与通用上传共用同一套规则。"""
    max_size_mb = MAX_UPLOAD_FILE_SIZE // 1024 // 1024
    return [
        FileRequired("file参数必须上传文件"),
        _FileNotEmpty(),
        FileAllowed(extensions, f"file参数只支持{'/'.join(extensions)}格式的文件"),
        FileSize(MAX_UPLOAD_FILE_SIZE, message=f"file参数大小不能超过{max_size_mb}MB"),
    ]


class FileUploadReq(FlaskForm):
    """通用文件上传请求，用于知识库文档等业务文件。"""

    file = FileField("file", validators=_validators(ALLOWED_FILE_EXTENSION))


class ImageUploadReq(FlaskForm):
    """图片上传请求，用于 APP、工具、插件等的图标。"""

    file = FileField("file", validators=_validators(ALLOWED_IMAGE_EXTENSION))


class UploadFileResp(Schema):
    """上传文件响应，返回入库后的文件信息。"""

    id = fields.UUID()
    account_id = fields.UUID()
    name = fields.Str()
    key = fields.Str()
    size = fields.Int()
    extension = fields.Str()
    mime_type = fields.Str()
    created_at = fields.DateTime(format="iso")


__all__ = [
    "ALLOWED_FILE_EXTENSION",
    "FileUploadReq",
    "ImageUploadReq",
    "UploadFileResp",
]
