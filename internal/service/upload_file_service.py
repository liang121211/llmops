import hashlib
import uuid
from dataclasses import dataclass
from io import BytesIO
from typing import Any, ClassVar

import inject
from werkzeug.datastructures import FileStorage

from internal.model import UploadFile
from internal.service.base_service import BaseService
from internal.service.cos_service import CosService

# 文件内容使用的 hash 算法，保存后可用于识别重复文件
HASH_ALGORITHM = "sha256"


@inject.autoparams()
@dataclass
class UploadFileService(BaseService[UploadFile]):
    """上传文件服务层，负责把文件写入对象存储并保存文件信息。"""

    model: ClassVar[type[UploadFile]] = UploadFile
    cos_service: CosService

    def upload_file(
        self, account_id: Any, upload_type: str, file_storage: FileStorage
    ) -> UploadFile:
        """上传单个文件：读取内容算 hash，写入对象存储后把信息落库。"""
        # 表单校验里的 FileSize 会移动流的读取位置，这里先回到开头
        file_storage.stream.seek(0)
        data = file_storage.stream.read()
        extension = self._extension(file_storage.filename)
        key = self._key(upload_type, extension)
        self.cos_service.upload_file(key, BytesIO(data))
        return self.create(
            account_id=account_id,
            name=file_storage.filename or "",
            key=key,
            size=len(data),
            extension=extension,
            mime_type=file_storage.mimetype or "",
            hash=hashlib.new(HASH_ALGORITHM, data).hexdigest(),
        )

    def get_file_url(self, upload_file: UploadFile) -> str:
        """返回文件在对象存储里的实际访问地址。"""
        return self.cos_service.get_file_url(upload_file.key)

    @staticmethod
    def _extension(filename: str | None) -> str:
        """取出文件名里的小写扩展名，没有扩展名时返回空字符串。"""
        if not filename or "." not in filename:
            return ""
        return filename.rsplit(".", 1)[-1].lower()

    @staticmethod
    def _key(upload_type: str, extension: str) -> str:
        """生成对象存储里的文件路径，用 uuid 避免同名文件互相覆盖。"""
        name = uuid.uuid4().hex
        if not extension:
            return f"{upload_type}/{name}"
        return f"{upload_type}/{name}.{extension}"


__all__ = ["HASH_ALGORITHM", "UploadFileService"]
