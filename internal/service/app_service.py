import uuid
from dataclasses import dataclass
from typing import Any, ClassVar

import inject

from internal.model import App
from internal.service.base_service import BaseService

# 应用列表按创建时间倒序，最新的应用排在最前面
APP_ORDER = (App.created_at.desc(), App.id.desc())


@inject.autoparams()
@dataclass
class AppService(BaseService[App]):
    """应用服务层，通用读写继承自 BaseService，这里只保留应用特有的业务。"""

    model: ClassVar[type[App]] = App

    def create_app(
        self,
        name: str = "",
        icon: str = "",
        config: Any = None,
        account_id: Any = None,
    ) -> App:
        """新增应用，account_id 未指定时随机生成占位账号。"""
        return self.create(
            account_id=account_id if account_id is not None else uuid.uuid4(),
            name=name,
            icon=icon,
            config=config or {},
        )

    def get_apps(self) -> list[App]:
        """查询全部应用，按创建时间倒序。"""
        return self.get_list(order_by=APP_ORDER)

    def get_latest_app(self) -> App | None:
        """查询最新创建的应用，供无需传参的更新与删除使用。"""
        return self.get_first(order_by=APP_ORDER)


__all__ = ["AppService"]
