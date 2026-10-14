import uuid

import pytest
from sqlalchemy import func, select

from internal.model import App
from pkg.sqlalchemy import SQLAlchemy, db


def _count_by_account(account_id) -> int:
    """统计某个账号下的应用数量，用于断言提交与回滚的结果。"""
    stmt = select(func.count()).select_from(App).where(App.account_id == account_id)
    return db.session.execute(stmt).scalar()


def test_db_uses_wrapped_sqlalchemy():
    # 全局单例必须是二次封装后的类型，否则没有 auto_commit 可用
    assert type(db) is SQLAlchemy
    assert hasattr(db, "auto_commit")


def test_auto_commit_persists_changes(app_context):
    account_id = uuid.uuid4()

    with db.auto_commit():
        db.session.add(
            App(account_id=account_id, name="自动提交", icon="", config={"ok": 1})
        )

    # 退出上下文即已提交，后续查询能直接看到数据
    assert _count_by_account(account_id) == 1

    created = (
        db.session.execute(select(App).where(App.account_id == account_id))
        .scalars()
        .one()
    )
    with db.auto_commit():
        db.session.delete(created)

    assert _count_by_account(account_id) == 0


def test_auto_commit_rolls_back_on_error(app_context):
    account_id = uuid.uuid4()

    with pytest.raises(RuntimeError, match="boom"):
        with db.auto_commit():
            db.session.add(
                App(account_id=account_id, name="异常回滚", icon="", config={})
            )
            raise RuntimeError("boom")

    # 异常时事务回滚，数据不应落库
    assert _count_by_account(account_id) == 0
