from contextlib import contextmanager
from typing import Generator

from flask_sqlalchemy import SQLAlchemy as FlaskSQLAlchemy


class SQLAlchemy(FlaskSQLAlchemy):
    """二次封装 Flask 的 SQLAlchemy，提供自动提交的会话上下文。"""

    @contextmanager
    def auto_commit(self) -> Generator[None, None, None]:
        """上下文内只做增删改，正常退出时自动提交，异常时整体回滚。"""
        try:
            yield
            self.session.commit()
        except Exception:
            # 业务异常或提交失败都要回滚，避免半成品数据残留
            self.session.rollback()
            raise


__all__ = ["SQLAlchemy"]
