import logging

from celery import current_app

logger = logging.getLogger(__name__)


def _instance():
    import inject

    from internal.service.dataset_delete_service import DatasetDeleteService

    return inject.instance(DatasetDeleteService)


@current_app.task(bind=True, name="delete_dataset")
def delete_dataset_task(self, dataset_id: str) -> str:
    """异步级联删除知识库：文档、片段、关键词与向量数据全部清理。"""
    logger.info("开始删除知识库 %s", dataset_id)
    try:
        return _instance().delete_dataset(dataset_id)
    except Exception as e:
        logger.error("知识库 %s 删除失败：%s", dataset_id, e, exc_info=True)
        return f"failed: {e}"


__all__ = ["delete_dataset_task"]
