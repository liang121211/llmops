from dataclasses import dataclass

import inject
from langchain_core.retrievers import BaseRetriever

from config import Config
from internal.extension.weaviate_extension import get_weaviate
from internal.service.embedding_service import EmbeddingService


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


__all__ = ["VectorStoreService"]
