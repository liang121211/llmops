import logging

from celery import current_app

logger = logging.getLogger(__name__)


def _instance():
    import inject

    from internal.service.document_status_service import DocumentStatusService

    return inject.instance(DocumentStatusService)


@current_app.task(bind=True, name="disable_documents")
def disable_documents_task(self, document_ids: list[str]) -> str:
    """异步禁用文档：移除关键词、更新向量元数据、标记文档与片段。"""
    logger.info("开始禁用文档，共 %d 篇", len(document_ids))
    errors = _instance().disable_documents(document_ids)
    return f"disabled {len(document_ids) - len(errors)}/{len(document_ids)}, errors={errors}"


@current_app.task(bind=True, name="enable_documents")
def enable_documents_task(self, document_ids: list[str]) -> str:
    """异步启用文档：回填关键词、恢复向量元数据与数据库标记。"""
    logger.info("开始启用文档，共 %d 篇", len(document_ids))
    errors = _instance().enable_documents(document_ids)
    return f"enabled {len(document_ids) - len(errors)}/{len(document_ids)}, errors={errors}"


@current_app.task(bind=True, name="delete_documents")
def delete_documents_task(self, document_ids: list[str]) -> str:
    """异步删除文档：向量数据、关键词表引用、片段与文档记录全部清理。"""
    logger.info("开始删除文档，共 %d 篇", len(document_ids))
    errors = _instance().delete_documents(document_ids)
    return f"deleted {len(document_ids) - len(errors)}/{len(document_ids)}, errors={errors}"


__all__ = [
    "delete_documents_task",
    "disable_documents_task",
    "enable_documents_task",
]
