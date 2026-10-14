from unittest.mock import MagicMock, patch

import pytest

from internal.service.embedding_service import CachedEmbeddings


class _FakeEmbeddings:
    """模拟底层嵌入模型，记录调用次数。"""

    def __init__(self):
        self.doc_calls = 0
        self.query_calls = 0

    def embed_documents(self, texts):
        self.doc_calls += 1
        return [[float(i)] * 4 for i in range(len(texts))]

    def embed_query(self, text):
        self.query_calls += 1
        return [1.0, 2.0, 3.0, 4.0]


@pytest.fixture
def fake_embeddings():
    return _FakeEmbeddings()


@pytest.fixture
def cached(tmp_path, fake_embeddings):
    return CachedEmbeddings(fake_embeddings, str(tmp_path / "cache"))


def test_embed_documents_returns_vectors(cached):
    result = cached.embed_documents(["hello", "world"])

    assert len(result) == 2
    assert all(isinstance(v, list) for v in result)


def test_embed_documents_caches_results(cached, fake_embeddings):
    cached.embed_documents(["hello"])
    cached.embed_documents(["hello"])

    # 第二次应命中缓存，不再调用底层模型
    assert fake_embeddings.doc_calls == 1


def test_embed_documents_partial_cache(cached, fake_embeddings):
    cached.embed_documents(["hello"])
    cached.embed_documents(["hello", "world"])

    # 第一次调了1次（1条），第二次只算 world，又调1次
    assert fake_embeddings.doc_calls == 2


def test_embed_query_returns_vector(cached):
    result = cached.embed_query("test")

    assert isinstance(result, list)
    assert len(result) == 4


def test_embed_query_caches_result(cached, fake_embeddings):
    cached.embed_query("test")
    cached.embed_query("test")

    assert fake_embeddings.query_calls == 1


def test_cache_dir_created_automatically(tmp_path, fake_embeddings):
    cache_dir = tmp_path / "nested" / "cache"
    ce = CachedEmbeddings(fake_embeddings, str(cache_dir))
    ce.embed_query("auto")

    assert cache_dir.exists()
