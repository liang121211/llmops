import hashlib
import logging
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, ClassVar

import inject
from sqlalchemy import func, select

from internal.entity import SegmentStatus
from internal.lib.redis_lock import redis_lock, segment_enabled_lock_key
from internal.model.document import Document
from internal.model.segment import Segment
from internal.service.base_service import BaseService
from internal.service.keyword_table_service import KeywordTableService
from internal.service.vector_store_service import VectorStoreService
from pkg.paginator import Paginator, PaginatorReq
from pkg.sqlalchemy import SQLAlchemy

logger = logging.getLogger(__name__)

# 片段按位置升序排列，与构建顺序保持一致
SEGMENT_ORDER = (Segment.position.asc(), Segment.id.desc())


@inject.autoparams()
@dataclass
class SegmentService(BaseService[Segment]):
    """片段服务层，处理片段的查询、启用禁用与手动增删改。

    片段操作是同步执行的（不走 Celery），但并发防护与文档操作一致：
    先拿文档级片段启用锁（与文档禁用/启用互斥），再拿片段自身启用锁，
    词表内部另有关键词表锁。锁获取顺序始终是 文档锁 -> 片段锁，不会成环。
    """

    db: SQLAlchemy
    keyword_table_service: KeywordTableService
    vector_store_service: VectorStoreService
    model: ClassVar[type[Segment]] = Segment

    def get_latest_position(self, document_id: Any) -> int:
        """获取文档下最新的片段位置，不存在则返回 0。"""
        stmt = select(func.coalesce(func.max(Segment.position), 0)).where(
            Segment.document_id == document_id
        )
        return self.db.session.execute(stmt).scalar() or 0

    def get_segment_in_dataset(
        self, dataset_id: Any, document_id: Any, segment_id: Any
    ) -> Segment | None:
        """按 ID 获取片段，知识库或文档归属不符时视为不存在。"""
        segment = self.get_by_id(segment_id)
        if segment is None:
            return None
        if str(segment.dataset_id) != str(dataset_id):
            return None
        if str(segment.document_id) != str(document_id):
            return None
        return segment

    def get_segments_with_page(
        self, req: PaginatorReq, dataset_id: Any, document_id: Any
    ) -> dict:
        """分页查询文档下的片段列表，按位置正序排列。"""
        stmt = (
            select(Segment)
            .where(Segment.dataset_id == dataset_id, Segment.document_id == document_id)
            .order_by(*SEGMENT_ORDER)
        )
        page = Paginator.paginate(stmt, req)
        return page.dump()

    # ── 启用 / 禁用 ───────────────────────────────────────────────

    def disable_segment(
        self, dataset_id: Any, document_id: Any, segment_id: Any
    ) -> Segment:
        """禁用单个片段：词表移除关键词、向量元数据置为不可用。

        片段已处于禁用状态时抛 ValueError，由控制层转成业务错误。
        """
        with self._segment_locks(document_id, segment_id):
            segment = self._require_segment(dataset_id, document_id, segment_id)
            if not segment.enabled:
                raise ValueError("片段已处于禁用状态")
            self.keyword_table_service.remove_segments_keywords(
                segment.dataset_id, [str(segment.id)]
            )
            if segment.node_id:
                self.vector_store_service.update_segments_enabled(
                    [segment.node_id], False
                )
            with self.db.auto_commit():
                segment.enabled = False
                segment.disabled_at = datetime.now()
        logger.info("片段 %s 已禁用", segment_id)
        return segment

    def enable_segment(
        self, dataset_id: Any, document_id: Any, segment_id: Any
    ) -> Segment:
        """启用单个片段：回填关键词（所属文档启用时）、恢复向量元数据。

        片段已处于启用状态时抛 ValueError。
        """
        with self._segment_locks(document_id, segment_id):
            segment = self._require_segment(dataset_id, document_id, segment_id)
            if segment.enabled:
                raise ValueError("片段已处于启用状态")
            document = self.db.session.get(Document, segment.document_id)
            # 文档整体禁用时词表里不应有该片段关键词，等文档启用时统一回填
            if document is not None and document.enabled:
                self.keyword_table_service.add_segments_keywords(
                    segment.dataset_id,
                    {str(segment.id): list(segment.keywords or [])},
                )
            if segment.node_id:
                self.vector_store_service.update_segments_enabled(
                    [segment.node_id], True
                )
            with self.db.auto_commit():
                segment.enabled = True
                segment.disabled_at = None
        logger.info("片段 %s 已启用", segment_id)
        return segment

    # ── 新增 / 修改 / 删除 ────────────────────────────────────────

    def create_segment(
        self, document: Document, content: str, keywords: list[str]
    ) -> Segment:
        """手动新增片段：落库、写词表、向量化；向量写入失败时回滚全部改动。"""
        with redis_lock(segment_enabled_lock_key(document.id)):
            position = self.get_latest_position(document.id) + 1
            node_id = str(uuid.uuid4())
            segment = Segment(
                account_id=document.account_id,
                dataset_id=document.dataset_id,
                document_id=document.id,
                node_id=node_id,
                position=position,
                content=content,
                character_count=len(content),
                token_count=0,
                keywords=list(keywords),
                hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                status=SegmentStatus.COMPLETED,
                enabled=True,
            )
            with self.db.auto_commit():
                self.db.session.add(segment)
                # 先 flush 拿到客户端生成的主键，供词表与向量属性引用
                self.db.session.flush()

            keywords_written = False
            try:
                if document.enabled and keywords:
                    self.keyword_table_service.add_segments_keywords(
                        document.dataset_id, {str(segment.id): list(keywords)}
                    )
                    keywords_written = True
                self.vector_store_service.upsert_segment(
                    node_id,
                    content,
                    {
                        "document_id": str(document.id),
                        "dataset_id": str(document.dataset_id),
                        "segment_id": str(segment.id),
                        "document_enabled": document.enabled,
                        "segment_enabled": True,
                    },
                )
            except Exception as e:
                logger.error("片段向量写入失败，回滚片段 %s：%s", segment.id, e)
                self._rollback_new_segment(segment, keywords_written)
                raise
        logger.info("文档 %s 新增片段 %s（position=%s）", document.id, segment.id, position)
        return segment

    def update_segment(
        self,
        dataset_id: Any,
        document_id: Any,
        segment_id: Any,
        content: str,
        keywords: list[str],
    ) -> Segment:
        """修改片段内容与关键词：整组替换词表引用并重新向量化。"""
        with self._segment_locks(document_id, segment_id):
            segment = self._require_segment(dataset_id, document_id, segment_id)
            document = self.db.session.get(Document, segment.document_id)
            document_enabled = bool(document is not None and document.enabled)

            # 关键词整组替换：先摘掉旧引用，写回新内容后再按需回填
            self.keyword_table_service.remove_segments_keywords(
                segment.dataset_id, [str(segment.id)]
            )
            with self.db.auto_commit():
                segment.content = content
                segment.character_count = len(content)
                segment.hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                segment.keywords = list(keywords)
            if document_enabled and segment.enabled and keywords:
                self.keyword_table_service.add_segments_keywords(
                    segment.dataset_id, {str(segment.id): list(keywords)}
                )
            if segment.node_id:
                # 始终刷新向量内容：禁用中的片段也要保证启用后向量与正文一致
                self.vector_store_service.upsert_segment(
                    segment.node_id,
                    content,
                    {
                        "document_id": str(segment.document_id),
                        "dataset_id": str(segment.dataset_id),
                        "segment_id": str(segment.id),
                        "document_enabled": document_enabled,
                        "segment_enabled": segment.enabled,
                    },
                )
        logger.info("片段 %s 已更新", segment_id)
        return segment

    def delete_segment(
        self, dataset_id: Any, document_id: Any, segment_id: Any
    ) -> None:
        """删除片段：向量数据、词表引用、数据库行依次清理。"""
        with self._segment_locks(document_id, segment_id):
            segment = self._require_segment(dataset_id, document_id, segment_id)
            if segment.node_id:
                self.vector_store_service.delete_segments([segment.node_id])
            self.keyword_table_service.remove_segments_keywords(
                segment.dataset_id, [str(segment.id)]
            )
            with self.db.auto_commit():
                self.db.session.delete(segment)
        logger.info("片段 %s 已删除", segment_id)

    # ── 内部工具 ──────────────────────────────────────────────────

    @contextmanager
    def _segment_locks(self, document_id: Any, segment_id: Any):
        """组合文档级与片段级启用锁，保证与文档禁用/启用互斥。"""
        with redis_lock(segment_enabled_lock_key(document_id)):
            with redis_lock(segment_enabled_lock_key(segment_id)):
                yield

    def _require_segment(
        self, dataset_id: Any, document_id: Any, segment_id: Any
    ) -> Segment:
        """锁内重读片段并校验归属，等待锁期间可能已被并发修改。"""
        segment = self.get_by_id(segment_id)
        if segment is None or (
            str(segment.dataset_id) != str(dataset_id)
            or str(segment.document_id) != str(document_id)
        ):
            raise ValueError("片段不存在")
        # 拿锁前其他并发可能已提交，重新读取最新状态
        self.db.session.refresh(segment)
        return segment

    def _rollback_new_segment(self, segment: Segment, keywords_written: bool) -> None:
        """向量写入失败时撤销新片段及其词表引用。"""
        try:
            if keywords_written:
                self.keyword_table_service.remove_segments_keywords(
                    segment.dataset_id, [str(segment.id)]
                )
            with self.db.auto_commit():
                self.db.session.delete(segment)
        except Exception as cleanup_error:
            logger.error("片段 %s 回滚失败：%s", segment.id, cleanup_error)


__all__ = ["SegmentService"]
