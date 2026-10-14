import logging

from celery import current_app

logger = logging.getLogger(__name__)


@current_app.task(bind=True, name="download_embedding_model")
def download_embedding_model(self) -> str:
    """异步预下载嵌入模型，服务器启动后触发，避免首次请求阻塞。"""
    from internal.service.embedding_service import EmbeddingService

    import inject

    service = inject.instance(EmbeddingService)
    service.ensure_model_downloaded()
    return f"embedding model {service.model_name} ready"


__all__ = ["download_embedding_model"]
