import hashlib
import logging
import os
import pickle
import time
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


# 显式声明只注入 config；不写参数名的话 inject 会尝试注入所有字段，
# 包括带默认值的 _embeddings，从而实例化抽象类 Embeddings 报错
@inject.autoparams("config")
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

        logger.info("开始加载嵌入模型 %s，缓存目录 %s", self.model_name, self.cache_dir)
        load_start = time.monotonic()
        underlying = HuggingFaceEmbeddings(
            model_name=self.model_name,
            cache_folder=self.cache_dir,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        vector_cache = os.path.join(self.cache_dir, ".vector_cache")
        logger.info(
            "嵌入模型 %s 加载完成，耗时 %.1f 秒",
            self.model_name,
            time.monotonic() - load_start,
        )
        return CachedEmbeddings(underlying, vector_cache)

    def _cache_size_mb(self) -> float:
        """统计缓存目录总占用（MB），用于确认模型文件确实已落盘。"""
        total = 0
        for root, _dirs, files in os.walk(self.cache_dir):
            for name in files:
                try:
                    total += os.path.getsize(os.path.join(root, name))
                except OSError:
                    continue
        return total / 1024 / 1024

    def is_model_cached(self) -> bool:
        """检查模型文件是否已完整存在于本地缓存，不发起网络请求。"""
        try:
            from huggingface_hub import snapshot_download

            snapshot_download(
                repo_id=self.model_name,
                cache_dir=self.cache_dir,
                local_files_only=True,
            )
            return True
        except Exception:
            return False

    def ensure_model_downloaded(self) -> None:
        """确保模型已下载到本地，供启动时异步调用，带进度与结果日志。"""
        logger.info(
            "开始预下载嵌入模型 %s（缓存目录 %s，下载进度会显示在 worker 控制台）",
            self.model_name,
            self.cache_dir,
        )
        start = time.monotonic()
        try:
            # snapshot_download 自带 tqdm 进度条（Fetching xx files / 每个文件的 MB 数），
            # 下载完成后 get_embeddings 直接读本地缓存，不会再触发网络请求
            from huggingface_hub import snapshot_download

            snapshot_download(repo_id=self.model_name, cache_dir=self.cache_dir)
            logger.info(
                "嵌入模型 %s 文件下载完成，耗时 %.1f 秒",
                self.model_name,
                time.monotonic() - start,
            )
        except Exception as e:
            logger.warning("snapshot_download 失败，改为通过模型加载器下载：%s", e)
        self.get_embeddings()
        logger.info(
            "嵌入模型 %s 准备就绪，缓存占用 %.1f MB，总耗时 %.1f 秒",
            self.model_name,
            self._cache_size_mb(),
            time.monotonic() - start,
        )


__all__ = ["EmbeddingService", "CachedEmbeddings"]
