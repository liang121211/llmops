from pkg.sqlalchemy import db


class App(db.Model):
    """智能体应用 ORM 模型。"""

    __tablename__ = "app"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(64), nullable=False, default="draft")


__all__ = ["App"]
