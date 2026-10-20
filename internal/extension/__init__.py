from internal.extension.celery_extension import FlaskTask, init_celery
from internal.extension.database_extension import init_database
from internal.extension.inject_extension import init_inject
from internal.extension.logging_extension import init_logging
from internal.extension.migration_extension import MIGRATIONS_DIR, migrate
from internal.extension.redis_extension import init_redis
from internal.extension.weaviate_extension import get_weaviate, init_weaviate

# 登录扩展会牵出服务层与中间件，放在最后导入，避免包初始化时出现循环依赖
from internal.extension.login_extension import init_login

__all__ = [
    "FlaskTask",
    "MIGRATIONS_DIR",
    "get_weaviate",
    "init_celery",
    "init_database",
    "init_inject",
    "init_login",
    "init_logging",
    "init_redis",
    "init_weaviate",
    "migrate",
]
