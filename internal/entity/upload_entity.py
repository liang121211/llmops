# 允许上传的图片扩展名，用于 APP、工具、插件等图标
ALLOWED_IMAGE_EXTENSION = ["jpg", "jpeg", "png", "webp", "gif", "svg"]

# 允许上传的文档扩展名，用于知识库文档等业务文件
ALLOWED_DOCUMENT_EXTENSION = [
    "txt",
    "markdown",
    "md",
    "pdf",
    "html",
    "htm",
    "xlsx",
    "xls",
    "doc",
    "docx",
    "csv",
]

# 单个文件的大小上限：16MB
MAX_UPLOAD_FILE_SIZE = 16 * 1024 * 1024


class UploadFileType:
    """上传文件的业务类型，同时作为对象存储里的存放目录名。"""

    FILE = "file"  # 通用文件上传
    IMAGE = "image"  # 图片上传


class StorageType:
    """对象存储驱动，本地开发用 MinIO，生产环境用腾讯云 COS。"""

    MINIO = "minio"
    COS = "cos"


class ProcessType:
    """文档处理类型：自动使用默认规则，手动需要提供自定义规则。"""

    AUTOMATIC = "automatic"
    CUSTOM = "custom"


# 单次最多上传的文档数量
MAX_DOCUMENT_BATCH_SIZE = 10

# 默认的自动处理规则
DEFAULT_PROCESS_RULE = {
    "segment": {
        "separators": ["\n\n", "\n", "。", ".", "！", "!", "？", "?"],
        "chunk_size": 500,
        "chunk_overlap": 50,
    },
    "pre_process_rules": [
        {"id": "remove_extra_space", "enabled": True},
        {"id": "remove_url_and_email", "enabled": True},
    ],
}


__all__ = [
    "ALLOWED_DOCUMENT_EXTENSION",
    "ALLOWED_IMAGE_EXTENSION",
    "DEFAULT_PROCESS_RULE",
    "MAX_DOCUMENT_BATCH_SIZE",
    "MAX_UPLOAD_FILE_SIZE",
    "ProcessType",
    "StorageType",
    "UploadFileType",
]
