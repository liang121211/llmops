from pkg.sqlalchemy import db


def init_database(app):
    """初始化 Flask-SQLAlchemy。"""
    db.init_app(app)


__all__ = ["init_database"]
