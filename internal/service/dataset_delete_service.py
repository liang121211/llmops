import logging
from dataclasses import dataclass

import inject
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select

from internal.entity import DOCUMENT_PROCESSING_STATUSES
from internal.lib.redis_lock import dataset_delete_lock_key, redis_lock
from internal.model.app_dataset_join import AppDatasetJoin
from internal.model.dataset import Dataset
from internal.model.document import Document
from internal.model.keyword_table import KeywordTable
from internal.model.segment import Segment
from internal.service.vector_store_service import VectorStoreService
from pkg.sqlalchemy import SQLAlchemy

logger = logging.getLogger(__name__)


@inject.autoparams()
@dataclass
class DatasetDeleteService:
    """知识库级联删除服务，在 Celery 任务中执行。

    删除顺序：向量数据 -> 关键词表 -> 片段 -> 文档 -> 应用关联 -> 知识库本体，
    先清外部存储再删数据库行，中途失败时数据库记录仍在，可重新触发删除。
    """

    db: SQLAlchemy
    vector_store_service: VectorStoreService

    def delete_dataset(self, dataset_id) -> str:
        """级联删除知识库的全部数据，返回结果摘要。"""
        with redis_lock(dataset_delete_lock_key(dataset_id)):
            dataset = self.db.session.get(Dataset, dataset_id)
            if dataset is None:
                raise ValueError(f"知识库 {dataset_id} 不存在")

            # 与文档删除一致：存在处理中的文档时拒绝，避免与构建任务互相踩踏
            processing = self._count_processing_documents(dataset_id)
            if processing:
                raise RuntimeError(
                    f"知识库下存在 {processing} 篇处理中的文档，不能删除"
                )

            node_ids = list(
                self.db.session.execute(
                    select(Segment.node_id).where(
                        Segment.dataset_id == dataset_id, Segment.node_id != ""
                    )
                ).scalars().all()
            )
            self.vector_store_service.delete_segments(node_ids)

            document_count = self._count(
                select(func.count()).select_from(Document).where(
                    Document.dataset_id == dataset_id
                )
            )
            segment_count = self._count(
                select(func.count()).select_from(Segment).where(
                    Segment.dataset_id == dataset_id
                )
            )
            with self.db.auto_commit():
                self.db.session.execute(
                    sa_delete(KeywordTable).where(
                        KeywordTable.dataset_id == dataset_id
                    )
                )
                self.db.session.execute(
                    sa_delete(Segment).where(Segment.dataset_id == dataset_id)
                )
                self.db.session.execute(
                    sa_delete(Document).where(Document.dataset_id == dataset_id)
                )
                self.db.session.execute(
                    sa_delete(AppDatasetJoin).where(
                        AppDatasetJoin.dataset_id == dataset_id
                    )
                )
                self.db.session.execute(
                    sa_delete(Dataset).where(Dataset.id == dataset_id)
                )

            summary = (
                f"deleted dataset={dataset_id} "
                f"documents={document_count} segments={segment_count} "
                f"vectors={len(node_ids)}"
            )
            logger.info("知识库 %s 级联删除完成：%s", dataset_id, summary)
            return summary

    def _count_processing_documents(self, dataset_id) -> int:
        """统计知识库中仍在构建流程里的文档数量。"""
        stmt = (
            select(func.count())
            .select_from(Document)
            .where(
                Document.dataset_id == dataset_id,
                Document.status.in_(DOCUMENT_PROCESSING_STATUSES),
            )
        )
        return self.db.session.execute(stmt).scalar() or 0

    def _count(self, stmt) -> int:
        return self.db.session.execute(stmt).scalar() or 0


__all__ = ["DatasetDeleteService"]
