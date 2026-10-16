import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy import delete as sa_delete, select

from internal.entity import DocumentStatus, SegmentStatus
from internal.model.app_dataset_join import AppDatasetJoin
from internal.model.dataset import Dataset
from internal.model.document import Document
from internal.model.keyword_table import KeywordTable
from internal.model.process_rule import ProcessRule
from internal.model.segment import Segment
from internal.pkg.response.http_code import HttpCode
from internal.service.dataset_service import DatasetService


class TestDatasetDeleteAPI:
    """知识库删除接口测试：只做前置校验并提交异步任务。"""

    @pytest.fixture(autouse=True)
    def setup(self, client, app_context, monkeypatch):
        from pkg.sqlalchemy import db

        self.client = client
        self.db = db
        self.submitted = []

        def _fake_trigger(self_service, dataset_id):
            self.submitted.append(str(dataset_id))

        # autoparams 包装后真实类在 __wrapped__
        monkeypatch.setattr(DatasetService.__wrapped__, "trigger_delete", _fake_trigger)

        self.account_id = uuid.UUID("a666a888-8888-6666-1234-b9d69212aaaa")
        self.dataset_id = uuid.uuid4()
        with db.auto_commit():
            db.session.add(
                Dataset(
                    id=self.dataset_id,
                    account_id=self.account_id,
                    name=f"ds_del_api_{self.dataset_id.hex[:8]}",
                    description="test",
                )
            )
        yield
        with db.auto_commit():
            db.session.execute(sa_delete(Dataset).where(Dataset.id == self.dataset_id))

    def _add_document(self, status):
        from internal.model.process_rule import ProcessRule as PR

        with self.db.auto_commit():
            pr = PR(
                account_id=self.account_id,
                dataset_id=self.dataset_id,
                mode="automatic",
                rule={},
            )
            self.db.session.add(pr)
            self.db.session.flush()
            doc = Document(
                account_id=self.account_id,
                dataset_id=self.dataset_id,
                upload_file_id=uuid.uuid4(),
                process_rule_id=pr.id,
                batch="2026101500000012121212",
                name="del_api.txt",
                position=1,
                status=status,
                enabled=True,
            )
            self.db.session.add(doc)
        self._process_rule_id = pr.id
        return doc

    def _cleanup_documents(self):
        with self.db.auto_commit():
            self.db.session.execute(
                sa_delete(Document).where(Document.dataset_id == self.dataset_id)
            )
            if hasattr(self, "_process_rule_id"):
                self.db.session.execute(
                    sa_delete(ProcessRule).where(
                        ProcessRule.id == self._process_rule_id
                    )
                )

    def test_delete_submits_async_task(self):
        body = self.client.delete(f"/datasets/{self.dataset_id}").get_json()
        assert body["code"] == HttpCode.SUCCESS.value
        assert body["data"]["id"] == str(self.dataset_id)
        assert self.submitted == [str(self.dataset_id)]

    def test_delete_not_found(self):
        body = self.client.delete(f"/datasets/{uuid.uuid4()}").get_json()
        assert body["code"] == HttpCode.NOT_FOUND.value
        assert self.submitted == []

    def test_delete_rejected_when_documents_processing(self):
        doc = self._add_document(DocumentStatus.PARSING)
        body = self.client.delete(f"/datasets/{self.dataset_id}").get_json()
        assert body["code"] == HttpCode.FAIL.value
        assert "处理中" in body["message"]
        assert self.submitted == []
        self._cleanup_documents()

    def test_delete_allowed_when_documents_completed(self):
        self._add_document(DocumentStatus.COMPLETED)
        body = self.client.delete(f"/datasets/{self.dataset_id}").get_json()
        assert body["code"] == HttpCode.SUCCESS.value
        assert self.submitted == [str(self.dataset_id)]
        self._cleanup_documents()


class TestDatasetDeleteService:
    """知识库级联删除服务测试，向量删除以 mock 替代。"""

    @pytest.fixture(autouse=True)
    def setup(self, app_context):
        from pkg.sqlalchemy import db

        self.db = db
        self.account_id = uuid.UUID("a666a888-8888-6666-1234-b9d69212aaaa")
        self.dataset_id = uuid.uuid4()
        self.vector_mock = MagicMock()

        from internal.service.dataset_delete_service import DatasetDeleteService

        self.service = DatasetDeleteService(
            db=db, vector_store_service=self.vector_mock
        )

        with db.auto_commit():
            db.session.add(
                Dataset(
                    id=self.dataset_id,
                    account_id=self.account_id,
                    name=f"ds_del_svc_{self.dataset_id.hex[:8]}",
                    description="test",
                )
            )
            pr = ProcessRule(
                account_id=self.account_id,
                dataset_id=self.dataset_id,
                mode="automatic",
                rule={},
            )
            db.session.add(pr)
            db.session.flush()
            self.process_rule_id = pr.id
            doc = Document(
                account_id=self.account_id,
                dataset_id=self.dataset_id,
                upload_file_id=uuid.uuid4(),
                process_rule_id=pr.id,
                batch="2026101500000034343434",
                name="del_svc.txt",
                position=1,
                status=DocumentStatus.COMPLETED,
                enabled=True,
            )
            db.session.add(doc)
            db.session.flush()
            self.document_id = doc.id
            seg = Segment(
                account_id=self.account_id,
                dataset_id=self.dataset_id,
                document_id=doc.id,
                node_id=str(uuid.uuid4()),
                position=0,
                content="内容",
                character_count=2,
                keywords=["词"],
                status=SegmentStatus.COMPLETED,
                enabled=True,
            )
            db.session.add(seg)
            db.session.flush()
            self.node_id = seg.node_id
            db.session.add(
                AppDatasetJoin(app_id=uuid.uuid4(), dataset_id=self.dataset_id)
            )

        # 词表里放该知识库与另一个知识库的数据，验证只删自己的
        with db.auto_commit():
            db.session.add(
                KeywordTable(
                    dataset_id=self.dataset_id,
                    keyword_table={"词": [str(self.document_id)]},
                )
            )
        yield

        with db.auto_commit():
            db.session.execute(
                sa_delete(Segment).where(Segment.dataset_id == self.dataset_id)
            )
            db.session.execute(
                sa_delete(Document).where(Document.dataset_id == self.dataset_id)
            )
            db.session.execute(
                sa_delete(ProcessRule).where(ProcessRule.id == self.process_rule_id)
            )
            db.session.execute(
                sa_delete(AppDatasetJoin).where(
                    AppDatasetJoin.dataset_id == self.dataset_id
                )
            )
            db.session.execute(
                sa_delete(KeywordTable).where(
                    KeywordTable.dataset_id == self.dataset_id
                )
            )
            db.session.execute(
                sa_delete(Dataset).where(Dataset.id == self.dataset_id)
            )

    def _exists(self, model, condition):
        return (
            self.db.session.execute(
                select(model).where(condition).limit(1)
            ).first()
            is not None
        )

    def test_delete_cascades_all_data(self):
        summary = self.service.delete_dataset(self.dataset_id)
        assert "deleted" in summary
        self.db.session.expire_all()
        assert not self._exists(Dataset, Dataset.id == self.dataset_id)
        assert not self._exists(Document, Document.dataset_id == self.dataset_id)
        assert not self._exists(Segment, Segment.dataset_id == self.dataset_id)
        assert not self._exists(
            KeywordTable, KeywordTable.dataset_id == self.dataset_id
        )
        assert not self._exists(
            AppDatasetJoin, AppDatasetJoin.dataset_id == self.dataset_id
        )
        self.vector_mock.delete_segments.assert_called_once_with([self.node_id])

    def test_delete_rejects_processing_documents(self):
        with self.db.auto_commit():
            doc = self.db.session.get(Document, self.document_id)
            doc.status = DocumentStatus.INDEXING
        with pytest.raises(RuntimeError, match="不能删除"):
            self.service.delete_dataset(self.dataset_id)
        self.db.session.expire_all()
        assert self._exists(Dataset, Dataset.id == self.dataset_id)
        self.vector_mock.delete_segments.assert_not_called()
        with self.db.auto_commit():
            doc = self.db.session.get(Document, self.document_id)
            doc.status = DocumentStatus.COMPLETED

    def test_delete_missing_dataset_raises(self):
        with pytest.raises(ValueError, match="不存在"):
            self.service.delete_dataset(uuid.uuid4())
