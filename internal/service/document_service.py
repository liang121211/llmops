import logging
import random
from dataclasses import dataclass
from datetime import datetime
from typing import Any, ClassVar, List
from uuid import UUID

import inject
from sqlalchemy import func, select

from internal.entity import DEFAULT_PROCESS_RULE, DocumentStatus, ProcessType
from internal.model.document import Document
from internal.model.process_rule import ProcessRule
from internal.model.upload_file import UploadFile
from internal.service.base_service import BaseService
from pkg.paginator import Paginator, PaginatorReq
from pkg.sqlalchemy import SQLAlchemy

logger = logging.getLogger(__name__)

# 知识库下的文档按位置升序排列，与批量创建顺序保持一致
DOCUMENT_ORDER = (Document.position.asc(), Document.id.desc())


def _generate_batch() -> str:
    """生成批次标识：时间戳 + 8位随机数。"""
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    rand = random.randint(10000000, 99999999)
    return f"{ts}{rand}"


@inject.autoparams()
@dataclass
class DocumentService(BaseService[Document]):
    """文档服务层，处理文档集的创建、查询与构建触发。"""

    db: SQLAlchemy
    model: ClassVar[type[Document]] = Document

    def get_latest_position(self, dataset_id: Any) -> int:
        """获取知识库下最新的文档位置，不存在则返回 0。"""
        stmt = select(func.coalesce(func.max(Document.position), 0)).where(
            Document.dataset_id == dataset_id
        )
        return self.db.session.execute(stmt).scalar() or 0

    def create_documents(
        self,
        account_id: Any,
        dataset_id: Any,
        upload_file_ids: List[str],
        process_type: str,
        rule: dict | None = None,
    ) -> tuple[list[Document], str]:
        """根据上传文件记录批量创建文档，返回文档列表和批次号。"""
        if process_type == ProcessType.AUTOMATIC:
            effective_rule = DEFAULT_PROCESS_RULE
        else:
            effective_rule = rule

        process_rule = ProcessRule(
            account_id=account_id,
            dataset_id=dataset_id,
            mode=process_type,
            rule=effective_rule,
        )
        with self.db.auto_commit():
            self.db.session.add(process_rule)

        batch = _generate_batch()
        base_position = self.get_latest_position(dataset_id)

        uid_objects = [UUID(uid) for uid in upload_file_ids]
        upload_files = self.db.session.execute(
            select(UploadFile).where(UploadFile.id.in_(uid_objects))
        ).scalars().all()
        upload_file_map = {str(uf.id): uf for uf in upload_files}

        documents = []
        with self.db.auto_commit():
            for idx, uid in enumerate(upload_file_ids):
                uf = upload_file_map.get(uid)
                if uf is None:
                    continue
                doc = Document(
                    account_id=account_id,
                    dataset_id=dataset_id,
                    upload_file_id=uf.id,
                    process_rule_id=process_rule.id,
                    batch=batch,
                    name=uf.name,
                    position=base_position + idx + 1,
                    status=DocumentStatus.WAITING,
                    enabled=True,
                )
                self.db.session.add(doc)
                documents.append(doc)

        return documents, batch

    def trigger_build(self, document_ids: list[str]) -> None:
        """提交异步任务构建文档索引。"""
        from internal.task.build_documents_task import build_documents_task

        logger.info("提交文档构建任务，共 %d 篇文档", len(document_ids))
        build_documents_task.delay(document_ids)

    def trigger_disable(self, document_ids: list[str]) -> None:
        """提交异步任务禁用文档。"""
        from internal.task.document_status_task import disable_documents_task

        logger.info("提交文档禁用任务，共 %d 篇文档", len(document_ids))
        disable_documents_task.delay(document_ids)

    def trigger_enable(self, document_ids: list[str]) -> None:
        """提交异步任务启用文档。"""
        from internal.task.document_status_task import enable_documents_task

        logger.info("提交文档启用任务，共 %d 篇文档", len(document_ids))
        enable_documents_task.delay(document_ids)

    def trigger_delete(self, document_ids: list[str]) -> None:
        """提交异步任务删除文档。"""
        from internal.task.document_status_task import delete_documents_task

        logger.info("提交文档删除任务，共 %d 篇文档", len(document_ids))
        delete_documents_task.delay(document_ids)

    def get_documents_by_batch(self, dataset_id: Any, batch: str) -> list[Document]:
        """根据知识库 ID 和批次号获取该批次下的所有文档。"""
        stmt = (
            select(Document)
            .where(Document.dataset_id == dataset_id, Document.batch == batch)
            .order_by(Document.position.asc())
        )
        return list(self.db.session.execute(stmt).scalars().all())

    def get_documents_with_page(self, req: PaginatorReq, dataset_id: Any) -> dict:
        """分页查询知识库下的文档列表，按位置正序排列。"""
        stmt = (
            select(Document)
            .where(Document.dataset_id == dataset_id)
            .order_by(*DOCUMENT_ORDER)
        )
        page = Paginator.paginate(stmt, req)
        return page.dump()

    def get_document_in_dataset(
        self, dataset_id: Any, document_id: Any
    ) -> Document | None:
        """按 ID 获取文档，不属于该知识库时视为不存在。"""
        document = self.get_by_id(document_id)
        if document is None or str(document.dataset_id) != str(dataset_id):
            return None
        return document


__all__ = ["DocumentService"]
