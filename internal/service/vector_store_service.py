import logging
from dataclasses import dataclass

import inject
from langchain_core.retrievers import BaseRetriever

from config import Config
from internal.extension.weaviate_extension import get_weaviate
from internal.service.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


@inject.autoparams()
@dataclass
class VectorStoreService:
    """向量数据库服务，封装 Weaviate 集合操作与检索器获取。"""

    embedding_service: EmbeddingService
    config: Config

    @property
    def collection_name(self) -> str:
        return getattr(self.config, "WEAVIATE_COLLECTION", "llmops")

    @property
    def collection(self):
        """获取 Weaviate 原生集合对象。"""
        client = get_weaviate().client
        return client.collections.get(self.collection_name)

    def _get_vector_store(self):
        from langchain_weaviate import WeaviateVectorStore

        client = get_weaviate().client
        return WeaviateVectorStore(
            client=client,
            index_name=self.collection_name,
            text_key="text",
            embedding=self.embedding_service.get_embeddings(),
        )

    def get_retriever(self, **kwargs) -> BaseRetriever:
        """获取向量数据库转换的检索器，可传入 search_kwargs 等参数。"""
        vector_store = self._get_vector_store()
        return vector_store.as_retriever(**kwargs)

    def update_documents_enabled(self, node_ids: list[str], enabled: bool) -> None:
        """按 node_id 批量更新片段的 document_enabled 元数据。

        单个节点失败只记录日志不中断，禁用/启用是幂等操作，
        遗漏的节点可在下次启用/禁用时重新对齐。
        """
        if not node_ids:
            return
        collection = self.collection
        failed = 0
        for node_id in node_ids:
            try:
                # merge 是 PATCH 语义，只改动 document_enabled，向量与其它属性不动
                collection.data.merge(
                    node_id, properties={"document_enabled": enabled}
                )
            except Exception as e:
                failed += 1
                logger.warning("更新向量节点 %s 的启用状态失败：%s", node_id, e)
        logger.info(
            "向量库启用状态更新完成：%d 个节点（enabled=%s，失败 %d）",
            len(node_ids), enabled, failed,
        )

    def delete_segments(self, node_ids: list[str]) -> None:
        """按 node_id 批量删除向量库中的片段数据，节点不存在视为删除成功。"""
        if not node_ids:
            return
        collection = self.collection
        failed = 0
        for node_id in node_ids:
            try:
                collection.data.delete_by_id(node_id)
            except Exception as e:
                failed += 1
                logger.warning("删除向量节点 %s 失败：%s", node_id, e)
        logger.info(
            "向量库片段删除完成：%d 个节点（失败 %d）", len(node_ids), failed
        )

    def update_segments_enabled(self, node_ids: list[str], enabled: bool) -> None:
        """按 node_id 批量更新片段的 segment_enabled 元数据（片段级启用/禁用）。"""
        if not node_ids:
            return
        collection = self.collection
        for node_id in node_ids:
            # merge 是 PATCH 语义，只改动 segment_enabled
            collection.data.merge(
                node_id, properties={"segment_enabled": enabled}
            )
        logger.info(
            "向量库片段启用状态更新完成：%d 个节点（enabled=%s）",
            len(node_ids), enabled,
        )

    def upsert_segment(
        self, node_id: str, content: str, properties: dict
    ) -> None:
        """单条片段向量写入：先删旧节点再插入，内容与向量整体刷新。

        与批量操作不同，这里失败直接抛出，由调用方决定回滚策略。
        """
        embeddings = self.embedding_service.get_embeddings()
        vector = embeddings.embed_documents([content])[0]
        collection = self.collection
        try:
            collection.data.delete_by_id(node_id)
        except Exception as e:
            # 旧节点可能不存在（新建片段），删除失败不影响后续插入
            logger.debug("向量节点 %s 删除跳过：%s", node_id, e)
        collection.data.insert(
            properties={"text": content, **properties},
            uuid=node_id,
            vector=vector,
        )
        logger.info("向量片段 %s 已写入（node_id=%s）", properties.get("segment_id"), node_id)


__all__ = ["VectorStoreService"]
