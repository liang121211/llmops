import hashlib
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import inject
from langchain_core.documents import Document as LCDocument
from weaviate.collections.classes.data import DataObject

from internal.core.file_loader import FileLoader
from internal.core.keyword_extractor import extract_keywords
from internal.entity import DocumentStatus, SegmentStatus
from internal.model.document import Document
from internal.model.segment import Segment
from internal.service.embedding_service import EmbeddingService
from internal.service.keyword_table_service import KeywordTableService
from internal.service.process_rule_service import ProcessRuleService
from internal.service.vector_store_service import VectorStoreService
from pkg.sqlalchemy import SQLAlchemy

logger = logging.getLogger(__name__)

# 向量化线程池配置
_VECTORIZE_WORKERS = 4
_VECTORIZE_BATCH_SIZE = 20


@inject.autoparams()
@dataclass
class IndexBuildService:
    """文档索引构建服务，串联解析、切割、关键词提取、向量化全流程。"""

    db: SQLAlchemy
    file_loader: FileLoader
    process_rule_service: ProcessRuleService
    keyword_table_service: KeywordTableService
    embedding_service: EmbeddingService
    vector_store_service: VectorStoreService

    def build_documents(self, document_ids: list[Any]) -> None:
        """对一批文档执行完整的索引构建流程。"""
        for doc_id in document_ids:
            try:
                self._build_single_document(doc_id)
            except Exception as e:
                logger.error("文档 %s 构建失败：%s", doc_id, e, exc_info=True)
                self._mark_document_error(doc_id, str(e))

    def _build_single_document(self, document_id: Any) -> None:
        """单篇文档的完整构建流水线。"""
        doc = self.db.session.get(Document, document_id)
        if doc is None:
            logger.warning("文档 %s 不存在，跳过构建", document_id)
            return

        logger.info("开始构建文档 %s（%s）", doc.id, doc.name)
        self._update_document_status(doc, DocumentStatus.PARSING)

        # 1. 解析
        lc_docs = self._parsing(doc)

        # 2. 切割
        segments = self._splitting(doc, lc_docs)

        # 3. 索引构建（关键词提取 + 词表更新）
        self._indexing(doc, segments)

        # 4. 向量化存储
        self._completed(doc, segments)

        logger.info("文档 %s 构建完成", doc.id)

    def _parsing(self, doc: Document) -> list[LCDocument]:
        """解析文档为 LangChain 文档列表。"""
        start = datetime.now()
        upload_file = doc.upload_file
        if upload_file is None:
            raise ValueError(f"文档 {doc.id} 关联的上传文件不存在")

        lc_docs = self.file_loader.load_from_upload_file(
            upload_file, is_unstructured=True, return_text=False
        )
        total_chars = sum(len(d.page_content) for d in lc_docs)

        with self.db.auto_commit():
            doc.character_count = total_chars
            doc.parsing_completed_at = datetime.now()
            doc.status = DocumentStatus.SPLITTING

        elapsed = (datetime.now() - start).total_seconds()
        logger.info(
            "文档 %s 解析完成：共 %d 个文档块，%d 字符，耗时 %.2fs",
            doc.id, len(lc_docs), total_chars, elapsed,
        )
        return lc_docs

    def _splitting(self, doc: Document, lc_docs: list[LCDocument]) -> list[Segment]:
        """根据处理规则切割文档为片段并持久化。"""
        start = datetime.now()
        process_rule = doc.process_rule
        if process_rule is None:
            raise ValueError(f"文档 {doc.id} 关联的处理规则不存在")

        # 重建场景：先清理旧片段（向量、词表引用、DB 行），否则每次重跑都只追加造成重复
        self._cleanup_old_segments(doc)

        rule = process_rule.rule
        splitter = self.process_rule_service.get_text_splitter(rule)

        all_segments: list[Segment] = []
        position = 0

        for lc_doc in lc_docs:
            text = lc_doc.page_content
            cleaned = ProcessRuleService.pre_process_text(text, rule)
            if not cleaned.strip():
                continue

            chunks = splitter.split_text(cleaned)
            for chunk_text in chunks:
                chunk_text = chunk_text.strip()
                if not chunk_text:
                    continue
                node_id = str(uuid.uuid4())
                content_hash = hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()
                segment = Segment(
                    account_id=doc.account_id,
                    dataset_id=doc.dataset_id,
                    document_id=doc.id,
                    node_id=node_id,
                    position=position,
                    content=chunk_text,
                    character_count=len(chunk_text),
                    token_count=0,
                    keywords=[],
                    hash=content_hash,
                    status=SegmentStatus.WAITING,
                    enabled=True,
                )
                all_segments.append(segment)
                position += 1

        with self.db.auto_commit():
            for seg in all_segments:
                self.db.session.add(seg)

        total_tokens = sum(s.character_count for s in all_segments)
        with self.db.auto_commit():
            doc.token_count = total_tokens
            doc.splitting_completed_at = datetime.now()
            doc.status = DocumentStatus.INDEXING

        elapsed = (datetime.now() - start).total_seconds()
        logger.info(
            "文档 %s 切割完成：共 %d 个片段，耗时 %.2fs",
            doc.id, len(all_segments), elapsed,
        )
        return all_segments

    def _cleanup_old_segments(self, doc: Document) -> None:
        """重建前清理该文档的旧片段：向量数据、关键词表引用、DB 行。"""
        old_segments = (
            self.db.session.query(Segment)
            .filter(Segment.document_id == doc.id)
            .all()
        )
        if not old_segments:
            return

        node_ids = [s.node_id for s in old_segments if s.node_id]
        segment_ids = [str(s.id) for s in old_segments]
        # 先删向量再删词表最后删行：向量删除失败只告警不抛出，
        # 词表和 DB 行必须清干净，避免残留引用指向已不存在的片段
        self.vector_store_service.delete_segments(node_ids)
        self.keyword_table_service.remove_segments_keywords(doc.dataset_id, segment_ids)
        with self.db.auto_commit():
            for seg in old_segments:
                self.db.session.delete(seg)
        logger.info("文档 %s 重建前清理旧片段 %d 个", doc.id, len(old_segments))

    def _indexing(self, doc: Document, segments: list[Segment]) -> None:
        """提取关键词并更新关键词表（持分布式锁读-改-写）。"""
        start = datetime.now()
        keywords_map: dict[str, list[str]] = {}

        for seg in segments:
            kws = extract_keywords(seg.content)
            with self.db.auto_commit():
                seg.keywords = kws
                seg.status = SegmentStatus.PROCESSING
            keywords_map[str(seg.id)] = kws

        self.keyword_table_service.add_segments_keywords(doc.dataset_id, keywords_map)

        with self.db.auto_commit():
            doc.indexing_completed_at = datetime.now()
            doc.status = DocumentStatus.COMPLETED

        elapsed = (datetime.now() - start).total_seconds()
        keyword_total = sum(len(v) for v in keywords_map.values())
        logger.info(
            "文档 %s 索引构建完成：写入 %d 个关键词引用，耗时 %.2fs",
            doc.id, keyword_total, elapsed,
        )

    def _completed(self, doc: Document, segments: list[Segment]) -> None:
        """多线程向量化片段并存入向量数据库。"""
        start = datetime.now()
        embeddings = self.embedding_service.get_embeddings()
        collection = self.vector_store_service.collection

        errors: list[str] = []

        # 前面阶段 commit 后 ORM 对象已过期，而 Flask app context 是线程本地的，
        # 工作线程里再读 seg 属性会触发懒加载并报"Working outside of application
        # context"，所以必须在主线程预读全部属性，只给线程池传纯数据
        payloads = [
            (
                s.node_id,
                {
                    "text": s.content,
                    "document_id": str(s.document_id),
                    "dataset_id": str(s.dataset_id),
                    "segment_id": str(s.id),
                    "document_enabled": True,
                    "segment_enabled": True,
                },
            )
            for s in segments
        ]

        def _vectorize_batch(batch: list[tuple]) -> None:
            vectors = embeddings.embed_documents([props["text"] for _, props in batch])
            objects = [
                DataObject(uuid=node_id, properties=props, vector=vec)
                for (node_id, props), vec in zip(batch, vectors)
            ]
            if objects:
                collection.data.insert_many(objects)

        batches = [
            payloads[i:i + _VECTORIZE_BATCH_SIZE]
            for i in range(0, len(payloads), _VECTORIZE_BATCH_SIZE)
        ]

        with ThreadPoolExecutor(max_workers=_VECTORIZE_WORKERS) as executor:
            futures = {
                executor.submit(_vectorize_batch, batch): idx
                for idx, batch in enumerate(batches)
            }
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    future.result()
                except Exception as e:
                    err_msg = f"批次 {idx} 向量化失败：{e}"
                    logger.error(err_msg, exc_info=True)
                    errors.append(err_msg)

        now = datetime.now()
        if errors:
            error_msg = "; ".join(errors)
            with self.db.auto_commit():
                doc.status = DocumentStatus.ERROR
                doc.error = error_msg
                doc.completed_at = now
            for seg in segments:
                with self.db.auto_commit():
                    seg.status = SegmentStatus.ERROR
                    seg.error = error_msg
                    seg.completed_at = now
            raise RuntimeError(error_msg)
        else:
            with self.db.auto_commit():
                doc.status = DocumentStatus.COMPLETED
                doc.completed_at = now
            for seg in segments:
                with self.db.auto_commit():
                    seg.status = SegmentStatus.COMPLETED
                    seg.indexing_completed_at = now
                    seg.completed_at = now

        elapsed = (now - start).total_seconds()
        logger.info(
            "文档 %s 向量化完成：%d 个片段，%d 个批次，耗时 %.2fs",
            doc.id, len(segments), len(batches), elapsed,
        )

    def _update_document_status(self, doc: Document, status: str) -> None:
        """更新文档状态和处理开始时间。"""
        with self.db.auto_commit():
            doc.status = status
            doc.processing_started_at = datetime.now()

    def _mark_document_error(self, document_id: Any, error: str) -> None:
        """将文档标记为错误状态。"""
        doc = self.db.session.get(Document, document_id)
        if doc is None:
            return
        with self.db.auto_commit():
            doc.status = DocumentStatus.ERROR
            doc.error = error
            doc.stopped_at = datetime.now()


__all__ = ["IndexBuildService"]
