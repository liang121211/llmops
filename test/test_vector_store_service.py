from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_weaviate_client():
    client = MagicMock()
    collection = MagicMock()
    client.collections.get.return_value = collection
    return client, collection


@pytest.fixture
def vector_store_service(mock_weaviate_client):
    from internal.service.vector_store_service import VectorStoreService
    from internal.service.embedding_service import EmbeddingService
    from config import Config

    config = Config()
    embedding_service = MagicMock(spec=EmbeddingService)
    embedding_service.get_embeddings.return_value = MagicMock()

    service = VectorStoreService(
        embedding_service=embedding_service,
        config=config,
    )
    return service, mock_weaviate_client


def test_collection_name_from_config(vector_store_service):
    service, _ = vector_store_service
    assert service.collection_name == "llmops"


@patch("internal.service.vector_store_service.get_weaviate")
def test_collection_returns_native_collection(mock_get_weaviate, vector_store_service):
    service, (client, collection) = vector_store_service
    mock_fw = MagicMock()
    mock_fw.client = client
    mock_get_weaviate.return_value = mock_fw

    result = service.collection

    client.collections.get.assert_called_once_with("llmops")
    assert result == collection


@patch("internal.service.vector_store_service.get_weaviate")
@patch("internal.service.vector_store_service.WeaviateVectorStore", create=True)
def test_get_retriever_returns_retriever(mock_vs_class, mock_get_weaviate, vector_store_service):
    service, (client, _) = vector_store_service
    mock_fw = MagicMock()
    mock_fw.client = client
    mock_get_weaviate.return_value = mock_fw

    mock_vs_instance = MagicMock()
    mock_retriever = MagicMock()
    mock_vs_instance.as_retriever.return_value = mock_retriever
    mock_vs_class.return_value = mock_vs_instance

    # Need to patch the import inside the method
    with patch("langchain_weaviate.WeaviateVectorStore", mock_vs_class):
        retriever = service.get_retriever(search_kwargs={"k": 5})

    mock_vs_instance.as_retriever.assert_called_once_with(search_kwargs={"k": 5})
    assert retriever == mock_retriever
