from dataclasses import dataclass

import inject

from internal.core.file_loader import FileLoader
from internal.model.upload_file import UploadFile
from internal.pkg.response import not_found_message, success_json
from internal.service.upload_file_service import UploadFileService


@inject.autoparams()
@dataclass
class DocumentHandler:
    """文档加载控制层。"""

    upload_file_service: UploadFileService
    file_loader: FileLoader

    def load_document(self, upload_file_id):
        upload_file = self.upload_file_service.get_by_id(upload_file_id)
        if upload_file is None:
            return not_found_message("上传文件不存在")
        docs = self.file_loader.load_from_upload_file(upload_file, return_text=True)
        return success_json({"content": docs})


__all__ = ["DocumentHandler"]
