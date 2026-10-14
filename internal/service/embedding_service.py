import hashlib
import logging
import os
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import List

import inject
from langchain_core.embeddings import Embeddings

from config import Config

logger = logging.getLogger(__name__)


class CachedEmbeddings(Embeddings):
    """对底层嵌入模型加一层本地文件缓存，避免重复计算相同文本的向量。"""

    def __init__(self, underlying: Embeddings, cache_dir: str):
        self._underlying = underlying
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_key(self, text: str) -> Path:
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]
        return self._cache_dir / f"{h}.pkl"

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        results = []
        uncached_texts = []
        uncached_indices = []
        for i, text in enumerate(texts):
            path = self._cache_key(text)
            if path.exists():
                with open(path, "rb") as f:
                    results.append(pickle.load(f))
            else:
                uncached_texts.append(text)
                uncached_indices.append(i)
                results.append(None)
        if uncached_texts:
            vectors = self._underlying.embed_documents(uncached_texts)
            for idx, vec in zip(uncached_indices, vectors):
                results[idx] = vec
                path = self._cache_key(texts[idx])
                with open(path, "wb") as f:
                    pickle.dump(vec, f)
        return results

    def embed_query(self, text: str) -> List[float]:
        path = self._cache_key(text)
        if path.exists():
            with open(path, "rb") as f:
                return pickle.load(f)
        vec = self._underlying.embed_query(text)
        with open(path, "wb") as f:
            pickle.dump(vec, f)
        return vec


@inject.autoparams()
@dataclass
class EmbeddingService:
    """嵌入模型服务，负责加载 HuggingFace 模型并提供带缓存的嵌入能力。"""

    config: Config

    _embeddings: Embeddings | None = None

    @property
    def model_name(self) -> str:
        return getattr(self.config, "EMBEDDING_MODEL_NAME", "Qwen/Qwen3-Embedding-0.6B")

    @property
    def cache_dir(self) -> str:
        return getattr(self.config, "EMBEDDING_CACHE_DIR", "./internal/embeddings")

    def get_embeddings(self) -> Embeddings:
        """获取带缓存的嵌入模型实例，首次调用时加载模型。"""
        if self._embeddings is None:
            self._embeddings = self._load_embeddings()
        return self._embeddings

    def _load_embeddings(self) -> Embeddings:
        from langchain_huggingface import HuggingFaceEmbeddings

        logger.info("加载嵌入模型 %s，缓存目录 %s", self.model_name, self.cache_dir)
        underlying = HuggingFaceEmbeddings(
            model_name=self.model_name,
            cache_folder=self.cache_dir,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        vector_cache = os.path.join(self.cache_dir, ".vector_cache")
        return CachedEmbeddings(underlying, vector_cache)

    def ensure_model_downloaded(self) -> None:
        """确保模型已下载到本地，供启动时异步调用。"""
        logger.info("开始预下载嵌入模型 %s", self.model_name)
        self.get_embeddings()
        logger.info("嵌入模型 %s 准备就绪", self.model_name)


__all__ = ["EmbeddingService", "CachedEmbeddings"]
