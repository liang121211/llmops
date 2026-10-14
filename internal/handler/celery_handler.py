from dataclasses import dataclass

import inject
from flask import request

from internal.pkg.response import success_json, validate_error_json
from internal.schema.celery_schema import CreateDemoTaskReq
from internal.service.celery_service import CeleryService


@inject.autoparams()
@dataclass
class CeleryHandler:
    """Celery 异步任务控制层，提供 demo 任务的提交与结果查询接口。"""

    celery_service: CeleryService

    def create_demo_task(self):
        payload = request.get_json(silent=True) or {}
        form = CreateDemoTaskReq(formdata=None, data=payload)
        if not form.validate():
            return validate_error_json(form.errors)
        task_id = self.celery_service.submit_demo_task(form.seconds.data)
        return success_json({"task_id": task_id})

    def get_demo_task(self):
        task_id = request.args.get("task_id", "").strip()
        if not task_id:
            return validate_error_json({"task_id": ["task_id参数不能为空"]})
        result = self.celery_service.get_demo_task_result(task_id)
        return success_json(result)


__all__ = ["CeleryHandler"]
