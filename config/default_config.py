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
    "WEAVIATE_URL": os.getenv("WEAVIATE_URL", "http://localhost:8080"),
}


__all__ = ["DEFAULT_CONFIG"]
