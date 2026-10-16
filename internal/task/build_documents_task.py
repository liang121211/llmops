import logging

from celery import current_app

logger = logging.getLogger(__name__)


@current_app.task(bind=True, name="build_documents")
def build_documents_task(self, document_ids: list[str]) -> str:
    """异步构建文档索引：解析、切割、关键词提取、向量化存储。"""
    import inject

    from internal.service.index_build_service import IndexBuildService

    logger.info("开始构建文档索引，共 %d 篇文档", len(document_ids))
    service = inject.instance(IndexBuildService)
    service.build_documents(document_ids)
    logger.info("文档索引构建完成，共 %d 篇文档", len(document_ids))
    return f"built {len(document_ids)} documents"


__all__ = ["build_documents_task"]
