import logging
import uuid
from dataclasses import dataclass
from typing import Any, ClassVar

import inject
from sqlalchemy import func, select

from internal.entity import DOCUMENT_PROCESSING_STATUSES
from internal.model.dataset import Dataset
from internal.model.document import Document
from internal.service.base_service import BaseService
from pkg.paginator import Paginator, PaginatorReq
from pkg.sqlalchemy import SQLAlchemy

logger = logging.getLogger(__name__)

# 知识库列表按创建时间倒序，最新的排在最前面
DATASET_ORDER = (Dataset.created_at.desc(), Dataset.id.desc())

# 用户未填写描述时使用的默认模板
DEFAULT_DATASET_DESCRIPTION_FORMATTER = "当你要回答管理《{name}》问题时候你可以使用该知识库"


@inject.autoparams()
@dataclass
class DatasetService(BaseService[Dataset]):
    """知识库服务层，通用读写继承自 BaseService。"""

    db: SQLAlchemy
    model: ClassVar[type[Dataset]] = Dataset

    def create_dataset(
        self,
        name: str,
        icon: str = "",
        description: str = "",
        account_id: Any = None,
    ) -> Dataset:
        """新增知识库，同一账号下不允许同名。"""
        aid = account_id if account_id is not None else uuid.uuid4()
        # 未提供描述时使用默认模板
        if not description:
            description = DEFAULT_DATASET_DESCRIPTION_FORMATTER.format(name=name)
        return self.create(
            account_id=aid,
            name=name,
            icon=icon,
            description=description,
        )

    def exists_name(self, name: str, account_id: Any) -> bool:
        """检查同一账号下是否已存在同名知识库。"""
        return self.exists(Dataset.name == name, Dataset.account_id == account_id)

    def get_datasets_with_page(self, req: PaginatorReq, account_id: Any) -> dict:
        """分页查询当前账号的知识库列表。"""
        stmt = (
            select(Dataset)
            .where(Dataset.account_id == account_id)
            .order_by(*DATASET_ORDER)
        )
        page = Paginator.paginate(stmt, req)
        return page.dump()

    def get_datasets(self, account_id: Any) -> list[Dataset]:
        """查询当前账号的全部知识库。"""
        return self.get_list(
            Dataset.account_id == account_id, order_by=DATASET_ORDER
        )

    def has_processing_documents(self, dataset_id: Any) -> bool:
        """判断知识库下是否还有处于构建流程中的文档。"""
        stmt = (
            select(func.count())
            .select_from(Document)
            .where(
                Document.dataset_id == dataset_id,
                Document.status.in_(DOCUMENT_PROCESSING_STATUSES),
            )
        )
        return (self.db.session.execute(stmt).scalar() or 0) > 0

    def trigger_delete(self, dataset_id: Any) -> None:
        """提交异步任务级联删除知识库及其全部数据。"""
        from internal.task.dataset_task import delete_dataset_task

        logger.info("提交知识库删除任务：%s", dataset_id)
        delete_dataset_task.delay(str(dataset_id))


__all__ = ["DatasetService", "DEFAULT_DATASET_DESCRIPTION_FORMATTER"]
