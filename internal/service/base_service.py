from dataclasses import dataclass
from typing import Any, ClassVar, Generic, Sequence, TypeVar

from sqlalchemy import Select, select
from sqlalchemy.orm import DeclarativeBase

from pkg.sqlalchemy import SQLAlchemy

# 基类只针对单个 ORM 模型工作，子类用具体模型把类型固定下来
ModelT = TypeVar("ModelT", bound=DeclarativeBase)


@dataclass
class BaseService(Generic[ModelT]):
    """服务层基类，封装与各模型无关的通用增删改查。

    子类只需声明 model，简单的读写不必各自重复一遍；
    涉及默认值、排序、多表写入等业务时再覆盖或扩展。
    """

    db: SQLAlchemy
    # 子类操作的数据模型，声明为 ClassVar 避免变成构造参数
    model: ClassVar[type[DeclarativeBase]]

    def get_list(self, *conditions: Any, order_by: Sequence = ()) -> list:
        """查询符合条件的数据，可按列表达式排序。"""
        stmt = self._stmt(conditions, order_by)
        return list(self.db.session.execute(stmt).scalars().all())

    def get_first(self, *conditions: Any, order_by: Sequence = ()) -> ModelT | None:
        """查询符合条件的第一条数据，没有则返回 None。"""
        stmt = self._stmt(conditions, order_by)
        return self.db.session.execute(stmt).scalars().first()

    def exists(self, *conditions: Any) -> bool:
        """判断是否已经存在符合条件的数据。"""
        return self.get_first(*conditions) is not None

    def get_by_id(self, model_id: Any) -> ModelT | None:
        """按主键查询单条数据。"""
        return self.db.session.get(self.model, model_id)

    def create(self, **values: Any) -> ModelT:
        """新增一条数据并提交，返回模型实例。"""
        instance = self.model(**self._copied(values))
        # 只把写操作放进上下文，退出时由 auto_commit 统一提交
        with self.db.auto_commit():
            self.db.session.add(instance)
        return instance

    def update(self, model_id: Any, **values: Any) -> ModelT | None:
        """按主键更新数据，只覆盖显式传入的非空字段，找不到返回 None。"""
        instance = self.get_by_id(model_id)
        if instance is None:
            return None
        with self.db.auto_commit():
            for field, value in self._copied(values).items():
                # None 表示调用方没有给出该字段，保持原值
                if value is None:
                    continue
                setattr(instance, field, value)
        return instance

    def delete(self, model_id: Any) -> bool:
        """按主键删除数据，返回是否真正删除了数据。"""
        instance = self.get_by_id(model_id)
        if instance is None:
            return False
        with self.db.auto_commit():
            self.db.session.delete(instance)
        return True

    def _stmt(self, conditions: tuple[Any, ...], order_by: Sequence) -> Select:
        """按过滤条件与排序拼装查询语句。"""
        stmt = select(self.model)
        for condition in conditions:
            stmt = stmt.where(condition)
        for column in order_by:
            stmt = stmt.order_by(column)
        return stmt

    @staticmethod
    def _copied(values: dict[str, Any]) -> dict[str, Any]:
        """字典和列表复制一份，避免多行数据共用同一个引用。"""
        copied = {}
        for field, value in values.items():
            if isinstance(value, dict):
                value = dict(value)
            elif isinstance(value, list):
                value = list(value)
            copied[field] = value
        return copied


__all__ = ["BaseService"]
