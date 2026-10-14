import time
import logging

from celery import current_app

logger = logging.getLogger(__name__)


@current_app.task(bind=True, name="demo_task")
def demo_task(self, seconds: int = 5) -> str:
    """演示任务：sleep 指定秒数模拟耗时操作，用于验证 Celery worker 正常工作。"""
    logger.info("demo_task 开始执行，预计耗时 %d 秒", seconds)
    time.sleep(seconds)
    logger.info("demo_task 执行完成")
    return f"demo_task completed after {seconds}s"


__all__ = ["demo_task"]
