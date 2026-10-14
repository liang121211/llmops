from dotenv import load_dotenv

load_dotenv()

import inject
from flask_migrate import Migrate

from config import Config
from internal.core.file_loader import FileLoader
from internal.core.tools.api_tools import ApiProviderManager
from internal.core.tools.builtin_tools import (
    BuiltinCategoryManager,
    BuiltinProviderManager,
)
from internal.extension import migrate
from internal.handler.api_tool_handler import ApiToolHandler
from internal.handler.app_handler import AppHandler
from internal.handler.builtin_handler import BuiltinHandler
from internal.handler.celery_handler import CeleryHandler
from internal.handler.dataset_handler import DatasetHandler
from internal.handler.document_handler import DocumentHandler
from internal.handler.upload_file_handler import UploadFileHandler
from internal.router.router import Router
from internal.server.http import Http
from internal.service.api_tool_service import ApiToolService
from internal.service.builtin_service import BuiltinService
from internal.service.celery_service import CeleryService
from internal.service.cos_service import CosService
from internal.service.dataset_service import DatasetService
from internal.service.document_service import DocumentService
from internal.service.embedding_service import EmbeddingService
from internal.service.upload_file_service import UploadFileService
from internal.service.vector_store_service import VectorStoreService
from pkg.sqlalchemy import SQLAlchemy, db

# 配置对象全局唯一，既交给 Flask 也注入给需要读取配置的服务层
config = Config()


def _configure(binder):
    # AppService 注入的 db 必须是全局唯一的 SQLAlchemy 单例，不能新建实例
    binder.bind(SQLAlchemy, db)
    # 迁移实例同样全局唯一，绑定模块级对象供 Http 取用
    binder.bind(Migrate, migrate)
    # 对象存储服务按配置在 MinIO 与腾讯云 COS 之间切换，配置与 Flask 共用一份
    binder.bind(Config, config)
    binder.bind_to_constructor(AppHandler, AppHandler)
    binder.bind_to_constructor(BuiltinHandler, BuiltinHandler)
    binder.bind_to_constructor(ApiToolHandler, ApiToolHandler)
    binder.bind_to_constructor(UploadFileHandler, UploadFileHandler)
    binder.bind_to_constructor(CeleryHandler, CeleryHandler)
    binder.bind_to_constructor(DatasetHandler, DatasetHandler)
    binder.bind_to_constructor(DocumentHandler, DocumentHandler)
    binder.bind_to_constructor(BuiltinService, BuiltinService)
    binder.bind_to_constructor(ApiToolService, ApiToolService)
    binder.bind_to_constructor(UploadFileService, UploadFileService)
    binder.bind_to_constructor(CeleryService, CeleryService)
    binder.bind_to_constructor(DatasetService, DatasetService)
    binder.bind_to_constructor(DocumentService, DocumentService)
    binder.bind_to_constructor(EmbeddingService, EmbeddingService)
    binder.bind_to_constructor(VectorStoreService, VectorStoreService)
    # 自定义 API 工具管理器无状态，容器里保留一个实例给服务层复用
    binder.bind_to_constructor(ApiProviderManager, ApiProviderManager)
    binder.bind_to_constructor(CosService, CosService)
    binder.bind_to_constructor(FileLoader, FileLoader)
    binder.bind_to_constructor(Router, Router)
    # 两个插件管理器在容器里各只保留一个实例，Http 启动时初始化后全局复用
    binder.bind_to_constructor(BuiltinProviderManager, BuiltinProviderManager)
    binder.bind_to_constructor(BuiltinCategoryManager, BuiltinCategoryManager)


inject.clear_and_configure(_configure)

app = Http(
    inject.instance(Router),
    config,
    inject.instance(Migrate),
    inject.instance(BuiltinProviderManager),
    inject.instance(BuiltinCategoryManager),
)

# celery -A app.http.app.celery worker 需要模块级 celery 对象
celery = app.extensions["celery"]

# 导入 task 模块使 @celery.task 装饰的任务注册到 celery 实例
import internal.task.demo_task  # noqa: F401, E402
import internal.task.download_embedding_task  # noqa: F401, E402

# 服务器完全启动后异步预下载嵌入模型，避免首次请求长时间阻塞
if __name__ == "__main__":
    import logging

    logger = logging.getLogger(__name__)
    try:
        redis_client = app.extensions.get("redis")
        if redis_client is not None:
            redis_client.ping()
        from internal.task.download_embedding_task import download_embedding_model

        download_embedding_model.delay()
        logger.info("已提交嵌入模型预下载任务")
    except Exception as e:
        logger.warning("嵌入模型预下载任务提交失败（Redis 可能未启动）：%s", e)
    app.run()
