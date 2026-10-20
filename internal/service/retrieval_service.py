import logging
import uuid as uuid_module
from dataclasses import dataclass
from typing import Any

import inject
from sqlalchemy import select

from internal.core.keyword_extractor import extract_keywords
from internal.entity import (
    DEFAULT_HYBRID_WEIGHT,
    DEFAULT_SCORE_THRESHOLD,
    DEFAULT_TOP_K,
    QuerySource,
    RetrievalStrategy,
    SegmentStatus,
)
from internal.model.document import Document
from internal.model.segment import Segment
from internal.service.dataset_query_service import DatasetQueryService
from internal.service.keyword_table_service import KeywordTableService
from internal.service.vector_store_service import VectorStoreService
from pkg.sqlalchemy import SQLAlchemy

logger = logging.getLogger(__name__)


@inject.autoparams()
@dataclass
class RetrievalService:
    """知识库检索编排服务，串联全文检索、向量检索与混合检索。

    全文检索基于 jieba 提取查询关键词后在关键词倒排表里命中片段；
    向量检索委托给 VectorStoreService 的 near_vector 查询；
    混合检索把两路得分按权重融合后重新排序。
    """

    db: SQLAlchemy
    keyword_table_service: KeywordTableService
    vector_store_service: VectorStoreService
    dataset_query_service: DatasetQueryService

    def retrieve(
        self,
        dataset_id: Any,
        query: str,
        strategy: str = RetrievalStrategy.HYBRID,
        top_k: int = DEFAULT_TOP_K,
        score_threshold: float = DEFAULT_SCORE_THRESHOLD,
        hybrid_weight: float = DEFAULT_HYBRID_WEIGHT,
    ) -> list[dict]:
        """按策略检索知识库，返回带分数与文档信息的片段记录列表。

        strategy 为 vector/full_text/hybrid；score_threshold 过滤低分命中；
        hybrid_weight 是混合检索里全文一路的权重，向量为 (1-hybrid_weight)。
        """
        if not query or not query.strip():
            return []

        if strategy == RetrievalStrategy.VECTOR:
            scores = self._vector_scores(dataset_id, query, top_k)
        elif strategy == RetrievalStrategy.FULL_TEXT:
            scores = self._full_text_scores(dataset_id, query)
        else:
            scores = self._hybrid_scores(dataset_id, query, top_k, hybrid_weight)

        # 过滤低于最小匹配度的命中后按分数倒序，截取前 top_k 条
        filtered = {
            seg_id: score
            for seg_id, score in scores.items()
            if score >= score_threshold
        }
        ranked = sorted(filtered.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
        return self._build_records(dataset_id, ranked)

    def hit_testing(
        self,
        dataset_id: Any,
        query: str,
        account_id: Any,
        strategy: str = RetrievalStrategy.HYBRID,
        top_k: int = DEFAULT_TOP_K,
        score_threshold: float = DEFAULT_SCORE_THRESHOLD,
        hybrid_weight: float = DEFAULT_HYBRID_WEIGHT,
    ) -> list[dict]:
        """执行召回测试并写入一条知识库检索记录（来源为召回检索测试）。"""
        records = self.retrieve(
            dataset_id, query, strategy, top_k, score_threshold, hybrid_weight
        )
        self.dataset_query_service.record_query(
            dataset_id=dataset_id,
            query=query,
            source=QuerySource.RECALL_TEST,
            created_by=account_id,
        )
        return records

    # ── 各策略打分 ────────────────────────────────────────────────

    def _full_text_scores(self, dataset_id: Any, query: str) -> dict[str, float]:
        """全文检索打分：命中查询关键词数 / 查询关键词总数。"""
        keywords = extract_keywords(query)
        if not keywords:
            return {}
        matches = self.keyword_table_service.search_segments_by_keywords(
            dataset_id, keywords
        )
        total = len(keywords)
        return {
            segment_id: len(hit_keywords) / total
            for segment_id, hit_keywords in matches.items()
        }

    def _vector_scores(
        self, dataset_id: Any, query: str, limit: int
    ) -> dict[str, float]:
        """向量检索打分：取 Weaviate 近邻相似度，多召回一些再排序。"""
        fetch_limit = max(limit * 2, limit)
        hits = self.vector_store_service.search_by_vector(
            query, str(dataset_id), fetch_limit
        )
        scores: dict[str, float] = {}
        for hit in hits:
            segment_id = hit.get("segment_id")
            if segment_id:
                scores[str(segment_id)] = hit.get("score", 0.0)
        return scores

    def _hybrid_scores(
        self, dataset_id: Any, query: str, top_k: int, weight: float
    ) -> dict[str, float]:
        """混合检索打分：全文分 * weight + 向量分 * (1-weight)。

        某片段只被一路命中时，另一路得分按 0 计，天然降权。
        """
        full_text = self._full_text_scores(dataset_id, query)
        vector = self._vector_scores(dataset_id, query, top_k)
        segment_ids = set(full_text) | set(vector)
        combined: dict[str, float] = {}
        for segment_id in segment_ids:
            combined[segment_id] = (
                full_text.get(segment_id, 0.0) * weight
                + vector.get(segment_id, 0.0) * (1 - weight)
            )
        return combined

    # ── 结果拼装 ──────────────────────────────────────────────────

    def _build_records(
        self, dataset_id: Any, ranked: list[tuple[str, float]]
    ) -> list[dict]:
        """把 (segment_id, score) 列表补全为片段信息 + 文档信息 + 分数。"""
        if not ranked:
            return []
        segment_ids = [uuid_module.UUID(seg_id) for seg_id, _ in ranked]
        segments = self.db.session.execute(
            select(Segment).where(Segment.id.in_(segment_ids))
        ).scalars().all()
        segment_map = {str(seg.id): seg for seg in segments}

        records: list[dict] = []
        for segment_id, score in ranked:
            segment = segment_map.get(segment_id)
            if segment is None or not segment.enabled:
                continue
            if segment.status not in (SegmentStatus.COMPLETED,):
                # 未完成向量化的片段不参与召回结果
                continue
            records.append({
                "segment": {
                    "id": str(segment.id),
                    "document_id": str(segment.document_id),
                    "position": segment.position,
                    "content": segment.content,
                    "keywords": segment.keywords or [],
                    "hit_count": segment.hit_count,
                    "enabled": segment.enabled,
                    "status": segment.status,
                },
                "document": self._document_info(segment.document_id),
                "score": round(score, 6),
            })
        return records

    def _document_info(self, document_id: Any) -> dict:
        """取文档的 name 及其上传文件的 extension/mime_type。"""
        document = self.db.session.get(Document, document_id)
        if document is None:
            return {
                "id": str(document_id),
                "name": "",
                "extension": "",
                "mime_type": "",
            }
        upload_file = document.upload_file
        return {
            "id": str(document.id),
            "name": document.name,
            "extension": upload_file.extension if upload_file else "",
            "mime_type": upload_file.mime_type if upload_file else "",
        }


__all__ = ["RetrievalService"]
