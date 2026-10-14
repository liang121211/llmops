from pathlib import Path

from flask_migrate import Migrate

# 迁移脚本目录：<项目根>/internal/migration，这里是纯 Alembic 目录，不放 Python 代码
MIGRATIONS_DIR = str(Path(__file__).resolve().parents[1] / "migration")

# 全局唯一的迁移实例，由 Http 注入后完成初始化
migrate = Migrate()

__all__ = ["MIGRATIONS_DIR", "migrate"]
