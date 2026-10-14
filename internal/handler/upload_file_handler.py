from dataclasses import dataclass

import inject

from internal.entity import UploadFileType
from internal.pkg.response import success_json, validate_error_json
from internal.schema.upload_file_schema import (
    FileUploadReq,
    ImageUploadReq,
    UploadFileResp,
)
from internal.service.upload_file_service import UploadFileService


@inject.autoparams()
@dataclass
class UploadFileHandler:
    """上传文件控制层，提供通用文件上传与独立的图片上传接口。"""

    upload_file_service: UploadFileService

    def upload_file(self):
        # TODO: 等待授权认证模块完成后再进行切换调整
        account_id = "a666a888-8888-6666-1234-b9d69212aaaa"
        # 1. 校验上传的文件：扩展名白名单、大小上限、是否为空
        form = FileUploadReq()
        if not form.validate():
            return validate_error_json(form.errors)
        # 2. 服务层把文件写入对象存储并保存文件信息
        upload_file = self.upload_file_service.upload_file(
            account_id, UploadFileType.FILE, form.file.data
        )
        # 3. 用 marshmallow 拼装文件信息返回
        return success_json(UploadFileResp().dump(upload_file))

    def upload_image(self):
        # TODO: 等待授权认证模块完成后再进行切换调整
        account_id = "a666a888-8888-6666-1234-b9d69212aaaa"
        # 1. 图片上传只允许图片扩展名，其余规则与通用上传一致
        form = ImageUploadReq()
        if not form.validate():
            return validate_error_json(form.errors)
        upload_file = self.upload_file_service.upload_file(
            account_id, UploadFileType.IMAGE, form.file.data
        )
        # 2. 图片只需要返回可直接展示的实际访问地址
        return success_json(
            {"image_url": self.upload_file_service.get_file_url(upload_file)}
        )


__all__ = ["UploadFileHandler"]
