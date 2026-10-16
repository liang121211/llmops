import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import inject
from sqlalchemy import select

from internal.entity import DOCUMENT_PROCESSING_STATUSES, DocumentStatus
from internal.lib.redis_lock import (
    document_status_lock_key,
    redis_lock,
    segment_enabled_lock_key,
)
from internal.model.document import Document
from internal.model.segment import Segment
from internal.service.keyword_table_service import KeywordTableService
from internal.service.vector_store_service import VectorStoreService
from pkg.sqlalchemy import SQLAlchemy

logger = logging.getLogger(__name__)


@inject.autoparams()
@dataclass
class DocumentStatusService:
    """文档禁用/启用/删除服务，串联关键词表与向量库的联动操作。

    所有方法都在 Celery 任务里执行，多 worker 并发时用三层锁保护：
    文档状态锁（整篇文档互斥）→ 片段启用状态锁（词表+向量元数据区间）
    → 关键词表锁（在 KeywordTableService 内部）。
    """

    db: SQLAlchemy
    keyword_table_service: KeywordTableService
    vector_store_service: VectorStoreService

    def disable_documents(self, document_ids: list[Any]) -> list[str]:
        """批量禁用文档，返回失败的文档 ID 错误描述列表。"""
        return self._run_each(document_ids, self._disable_one, "禁用")

    def enable_documents(self, document_ids: list[Any]) -> list[str]:
        """批量启用文档，返回失败的文档 ID 错误描述列表。"""
        return self._run_each(document_ids, self._enable_one, "启用")

    def delete_documents(self, document_ids: list[Any]) -> list[str]:
        """批量删除文档，处理中的文档跳过，返回失败/跳过的描述列表。"""
        return self._run_each(document_ids, self._delete_one, "删除")

    # ── 内部实现 ──────────────────────────────────────────────────

    def _run_each(
        self, document_ids: list[Any], action, label: str
    ) -> list[str]:
        """逐篇执行操作，单篇失败不影响其余文档。"""
        errors: list[str] = []
        for doc_id in document_ids:
            try:
                with redis_lock(document_status_lock_key(doc_id)):
                    action(doc_id)
            except Exception as e:
                logger.error("文档 %s %s失败：%s", doc_id, label, e, exc_info=True)
                errors.append(f"{doc_id}: {e}")
        return errors

    def _get_document(self, document_id: Any) -> Document:
        doc = self.db.session.get(Document, document_id)
        if doc is None:
            raise ValueError(f"文档 {document_id} 不存在")
        return doc

    def _document_segments(self, document_id: Any) -> list[Segment]:
        stmt = (
            select(Segment)
            .where(Segment.document_id == document_id)
            .order_by(Segment.position.asc())
        )
        return list(self.db.session.execute(stmt).scalars().all())

    def _disable_one(self, document_id: Any) -> None:
        """禁用：移除该片段的关键词、向量元数据置为不可用、标记文档与片段。"""
        doc = self._get_document(document_id)
        if doc.status == DocumentStatus.DISABLED and not doc.enabled:
            logger.info("文档 %s 已是禁用状态，跳过", document_id)
            return
        segments = self._document_segments(doc.id)
        with redis_lock(segment_enabled_lock_key(doc.id)):
            self.keyword_table_service.remove_segments_keywords(
                doc.dataset_id, [str(seg.id) for seg in segments]
            )
            self.vector_store_service.update_documents_enabled(
                [seg.node_id for seg in segments if seg.node_id], False
            )
            with self.db.auto_commit():
                for seg in segments:
                    seg.enabled = False
        now = datetime.now()
        with self.db.auto_commit():
            doc.enabled = False
            doc.disabled_at = now
            doc.status = DocumentStatus.DISABLED
        logger.info("文档 %s（%s）已禁用：%d 个片段", doc.id, doc.name, len(segments))

    def _enable_one(self, document_id: Any) -> None:
        """启用：把片段关键词加回知识库词表、恢复向量元数据与数据库标记。"""
        doc = self._get_document(document_id)
        if doc.status == DocumentStatus.COMPLETED and doc.enabled:
            logger.info("文档 %s 已是启用状态，跳过", document_id)
            return
        segments = self._document_segments(doc.id)
        with redis_lock(segment_enabled_lock_key(doc.id)):
            keywords_map = {
                str(seg.id): list(seg.keywords or []) for seg in segments
            }
            self.keyword_table_service.add_segments_keywords(
                doc.dataset_id, keywords_map
            )
            self.vector_store_service.update_documents_enabled(
                [seg.node_id for seg in segments if seg.node_id], True
            )
            with self.db.auto_commit():
                for seg in segments:
                    seg.enabled = True
        with self.db.auto_commit():
            doc.enabled = True
            doc.disabled_at = None
            doc.status = DocumentStatus.COMPLETED
        logger.info("文档 %s（%s）已启用：%d 个片段", doc.id, doc.name, len(segments))

    def _delete_one(self, document_id: Any) -> None:
        """删除：向量数据 → 关键词表 → 片段行 → 文档行，处理中的文档拒绝。"""
        doc = self._get_document(document_id)
        if doc.status in DOCUMENT_PROCESSING_STATUSES:
            raise RuntimeError(
                f"文档 {document_id} 正在处理中（{doc.status}），不能删除"
            )
        segments = self._document_segments(doc.id)
        # 先清外部存储再删数据库行：中途失败时数据库记录还在，可以重新触发删除
        self.vector_store_service.delete_segments(
            [seg.node_id for seg in segments if seg.node_id]
        )
        self.keyword_table_service.remove_segments_keywords(
            doc.dataset_id, [str(seg.id) for seg in segments]
        )
        with self.db.auto_commit():
            for seg in segments:
                self.db.session.delete(seg)
            self.db.session.delete(doc)
        logger.info(
            "文档 %s（%s）已删除：%d 个片段", doc.id, doc.name, len(segments)
        )


__all__ = ["DocumentStatusService"]
