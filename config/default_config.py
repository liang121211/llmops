import os

from dotenv import load_dotenv

load_dotenv()

DEFAULT_CONFIG = {
    "SECRET_KEY": os.getenv("SECRET_KEY", "dev-secret-key"),
    "DEBUG": os.getenv("FLASK_DEBUG", "false").lower() == "true",
    "HOST": os.getenv("FLASK_HOST", "0.0.0.0"),
    "PORT": int(os.getenv("FLASK_PORT", "5000")),
    "SQLALCHEMY_DATABASE_URI": os.getenv(
        "SQLALCHEMY_DATABASE_URI",
        "postgresql+psycopg://postgres:postgres@localhost:5432/agent_platform",
    ),
    "SQLALCHEMY_TRACK_MODIFICATIONS": False,
    "MINIO_ENDPOINT": os.getenv("MINIO_ENDPOINT", "localhost:9000"),
    "MINIO_ACCESS_KEY": os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
    "MINIO_SECRET_KEY": os.getenv("MINIO_SECRET_KEY", "minioadmin"),
    "MINIO_BUCKET": os.getenv("MINIO_BUCKET", "agent-docs"),
    # 本地 MinIO 默认走 http，线上开启 TLS 时把 MINIO_SECURE 置为 true
    "MINIO_SECURE": os.getenv("MINIO_SECURE", "false").lower() == "true",
    "COS_SECRET_ID": os.getenv("COS_SECRET_ID", ""),
    "COS_SECRET_KEY": os.getenv("COS_SECRET_KEY", ""),
    "COS_REGION": os.getenv("COS_REGION", "ap-guangzhou"),
    "COS_SCHEME": os.getenv("COS_SCHEME", "https"),
    "COS_BUCKET": os.getenv("COS_BUCKET", ""),
    # 访问文件的域名，例如 https://xxx.cos.ap-guangzhou.myqcloud.com
    "COS_DOMAIN": os.getenv("COS_DOMAIN", ""),
    # 对象存储驱动：本地开发用 minio，生产环境用腾讯云 cos，可用 STORAGE_TYPE 覆盖
    "STORAGE_TYPE": os.getenv(
        "STORAGE_TYPE",
        "cos" if os.getenv("FLASK_ENV", "development") == "production" else "minio",
    ),
    "WEAVIATE_URL": os.getenv("WEAVIATE_URL", "http://localhost:8080"),
    # Weaviate 连接参数（flask-weaviate 优先读取这些细粒度配置）
    "WEAVIATE_HTTP_HOST": os.getenv("WEAVIATE_HTTP_HOST", "localhost"),
    "WEAVIATE_HTTP_PORT": int(os.getenv("WEAVIATE_HTTP_PORT", "8090")),
    "WEAVIATE_GRPC_HOST": os.getenv("WEAVIATE_GRPC_HOST", "localhost"),
    "WEAVIATE_GRPC_PORT": int(os.getenv("WEAVIATE_GRPC_PORT", "50051")),
    "WEAVIATE_COLLECTION": os.getenv("WEAVIATE_COLLECTION", "llmops"),
    # 嵌入模型配置
    "EMBEDDING_MODEL_NAME": os.getenv(
        "EMBEDDING_MODEL_NAME", "Qwen/Qwen3-Embedding-0.6B"
    ),
    "EMBEDDING_CACHE_DIR": os.getenv(
        "EMBEDDING_CACHE_DIR", "./internal/embeddings"
    ),
    # 日志配置：.env 里 LOGGINE_LEVEL 是历史拼写错误，这里同时兼容新旧键名
    "LOGGING_LEVEL": os.getenv(
        "LOGGING_LEVEL", os.getenv("LOGGINE_LEVEL", "INFO")
    ),
    "LOGGING_PATH": os.getenv("LOGGING_PATH", "./storage/logs/app.log"),
    "LOGGING_ENCODING": os.getenv("LOGGING_ENCODING", "utf-8"),
    "LOGGING_FORMATTER": os.getenv(
        "LOGGING_FORMATTER",
        "[%(asctime)s.%(msecs)03d] %(filename)s -> %(funcName)s "
        "line:%(lineno)d [%(levelname)s]: %(message)s",
    ),
    "LOGGING_TIME_ROTATING_WHEN": os.getenv(
        "LOGGING_TIME_ROTATING_WHEN", "midnight"
    ),
    "LOGGING_TIME_ROTATING_INTERVAL": int(
        os.getenv("LOGGING_TIME_ROTATING_INTERVAL", "1")
    ),
    "LOGGING_TIME_ROTATING_BACKUP_COUNT": int(
        os.getenv("LOGGING_TIME_ROTATING_BACKUP_COUNT", "30")
    ),
    # Redis 配置
    "REDIS_HOST": os.getenv("REDIS_HOST", "127.0.0.1"),
    "REDIS_PORT": int(os.getenv("REDIS_PORT", "6379")),
    "REDIS_USERNAME": os.getenv("REDIS_USERNAME", ""),
    "REDIS_PASSWORD": os.getenv("REDIS_PASSWORD", ""),
    "REDIS_DB": int(os.getenv("REDIS_DB", "0")),
    "REDIS_USE_SSL": os.getenv("REDIS_USE_SSL", "false").lower() == "true",
    # 分布式缓存锁的默认超时时间（秒），到期自动释放防止持有者崩溃造成死锁
    "REDIS_LOCK_TIMEOUT": int(os.getenv("REDIS_LOCK_TIMEOUT", "600")),
    # Celery 配置：broker 与 result_backend 共用 Redis 的不同 DB
    "CELERY_BROKER_DB": int(os.getenv("CELERY_BROKER_DB", "1")),
    "CELERY_RESULT_BACKEND_DB": int(os.getenv("CELERY_RESULT_BACKEND_DB", "1")),
    "CELERY_TASK_IGNORE_RESULT": os.getenv(
        "CELERY_TASK_IGNORE_RESULT", "false"
    ).lower()
    == "true",
    "CELERY_RESULT_EXPIRES": int(os.getenv("CELERY_RESULT_EXPIRES", "3600")),
    "CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP": os.getenv(
        "CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP", "false"
    ).lower()
    == "true",
    # 登录凭证配置：JWT 未单独配置密钥时复用 SECRET_KEY，默认有效期 30 天
    "JWT_SECRET_KEY": os.getenv("JWT_SECRET_KEY", os.getenv("SECRET_KEY", "dev-secret-key")),
    "JWT_ALGORITHM": os.getenv("JWT_ALGORITHM", "HS256"),
    "JWT_EXPIRE_DAYS": int(os.getenv("JWT_EXPIRE_DAYS", "30")),
}


__all__ = ["DEFAULT_CONFIG"]
