import traceback

from flask import Flask
from flask_migrate import Migrate

from config import Config
from internal.core.tools.builtin_tools import (
    BuiltinCategoryManager,
    BuiltinProviderManager,
)
from internal.exception import CustomException
from internal.extension import (
    MIGRATIONS_DIR,
    init_celery,
    init_database,
    init_logging,
    init_redis,
    init_weaviate,
)
from internal.model import (  # noqa: F401  导入即把全部 ORM 模型注册到 metadata
    ApiTool,
    ApiToolProvider,
    App,
    AppDatasetJoin,
    Dataset,
    DatasetQuery,
    Document,
    KeywordTable,
    ProcessRule,
    Segment,
    UploadFile,
)
from internal.pkg.response import HttpCode, Response, json
from internal.router.router import Router
from pkg.sqlalchemy import db


class Http(Flask):
    """继承 Flask 的 HTTP 服务，启动时完成配置加载与路由注册。"""

    def __init__(
        self,
        router: Router,
        config: Config,
        migrate: Migrate,
        provider_manager: BuiltinProviderManager,
        category_manager: BuiltinCategoryManager,
    ):
        super().__init__(__name__)
        # 将配置对象载入 Flask 配置
        self.config.from_object(config)
        # 日志要在路由注册前初始化，启动期的加载信息才能落到文件里
        init_logging(self)
        # Redis 连接在日志之后初始化，方便后续业务层通过 current_app.extensions 获取
        init_redis(self)
        # Celery 依赖 Redis 配置，放在 Redis 之后初始化
        init_celery(self)
        # Weaviate 向量数据库连接
        init_weaviate(self)
        self.register_error_handler(Exception, self._register_error_handler)
        # 初始化 SQLAlchemy
        init_database(self)
        # 建表全部交给 flask-migrate 维护，这里只注册迁移入口
        migrate.init_app(self, db, directory=MIGRATIONS_DIR)
        # 启动时先扫描插件广场的分类，再扫描 providers.yml 动态加载内置插件
        self.category_manager = category_manager.init()
        self.provider_manager = provider_manager.init()
        router.register_router(self)

    def _register_error_handler(self, error: Exception):
        if isinstance(error, CustomException):
            traceback.print_exception(type(error), error, error.__traceback__)
            return json(
                Response(
                    code=error.code,
                    message=error.message,
                    data=error.data,
                )
            )
        if self.debug:
            raise error
        return json(
            Response(
                code=HttpCode.FAIL,
                message=str(error),
                data={},
            )
        )


__all__ = ["Http"]
