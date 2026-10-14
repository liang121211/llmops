import random
from dataclasses import dataclass
from datetime import datetime
from typing import Any, ClassVar, List
from uuid import UUID

import inject
from sqlalchemy import func, select

from internal.entity import DEFAULT_PROCESS_RULE, ProcessType
from internal.model.document import Document
from internal.model.process_rule import ProcessRule
from internal.model.upload_file import UploadFile
from internal.service.base_service import BaseService
from pkg.sqlalchemy import SQLAlchemy


def _generate_batch() -> str:
    """生成批次标识：时间戳 + 8位随机数。"""
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    rand = random.randint(10000000, 99999999)
    return f"{ts}{rand}"


@inject.autoparams()
@dataclass
class DocumentService(BaseService[Document]):
    """文档服务层，处理文档集的创建与查询。"""

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
        # 确定处理规则
        if process_type == ProcessType.AUTOMATIC:
            effective_rule = DEFAULT_PROCESS_RULE
        else:
            effective_rule = rule

        # 创建处理规则记录
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

        # 查询所有上传文件记录
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
                    status="waiting",
                    enabled=True,
                )
                self.db.session.add(doc)
                documents.append(doc)

        return documents, batch


__all__ = ["DocumentService"]
