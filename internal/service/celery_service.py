from dataclasses import dataclass

import inject
from celery.result import AsyncResult

from internal.task.demo_task import demo_task


@inject.autoparams()
@dataclass
class CeleryService:
    """Celery 任务服务层，封装 demo 任务的提交与结果查询。"""

    def submit_demo_task(self, seconds: int) -> str:
        """提交 demo 任务到 Celery broker，返回 task_id。"""
        result = demo_task.delay(seconds)
        return result.id

    def get_demo_task_result(self, task_id: str) -> dict:
        """查询 demo 任务的执行状态与结果。"""
        result = AsyncResult(task_id, app=demo_task.app)
        if result.state == "PENDING":
            return {"state": "PENDING", "result": None}
        if result.state == "FAILURE":
            return {"state": "FAILURE", "result": str(result.result)}
        return {"state": result.state, "result": result.result}


__all__ = ["CeleryService"]
