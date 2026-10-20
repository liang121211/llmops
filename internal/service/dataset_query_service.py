import logging
from dataclasses import dataclass
from typing import Any, ClassVar

import inject
from sqlalchemy import desc, select

from internal.entity import DEFAULT_QUERY_RECORD_LIMIT
from internal.model.dataset_query import DatasetQuery
from internal.service.base_service import BaseService
from pkg.sqlalchemy import SQLAlchemy

logger = logging.getLogger(__name__)


@inject.autoparams()
@dataclass
class DatasetQueryService(BaseService[DatasetQuery]):
    """知识库检索记录服务，负责写入查询记录与查询最近记录。"""

    db: SQLAlchemy
    model: ClassVar[type[DatasetQuery]] = DatasetQuery

    def record_query(
        self,
        dataset_id: Any,
        query: str,
        source: str,
        created_by: Any,
        source_app_id: Any = None,
    ) -> DatasetQuery:
        """保存一条知识库检索记录。

        created_by 为发起查询的账号 ID；source_app_id 仅 App 来源时填写，
        召回测试与 Debugger 场景留空。
        """
        record = self.create(
            dataset_id=dataset_id,
            query=query,
            source=source,
            created_by=created_by,
            source_app_id=source_app_id,
        )
        logger.info("知识库 %s 记录检索：source=%s query=%s", dataset_id, source, query)
        return record

    def get_recent_by_dataset(
        self, dataset_id: Any, limit: int = DEFAULT_QUERY_RECORD_LIMIT
    ) -> list[DatasetQuery]:
        """查询知识库最近的检索记录，按创建时间倒序，默认返回 10 条。"""
        stmt = (
            select(DatasetQuery)
            .where(DatasetQuery.dataset_id == dataset_id)
            .order_by(desc(DatasetQuery.created_at))
            .limit(limit)
        )
        return list(self.db.session.execute(stmt).scalars().all())


__all__ = ["DatasetQueryService"]
