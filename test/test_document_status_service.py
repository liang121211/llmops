import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy import delete, select

from internal.entity import DocumentStatus
from internal.model.document import Document
from internal.model.segment import Segment


class TestDocumentStatusService:
    """文档禁用/启用/删除服务测试，向量库操作以 mock 替代。"""

    @pytest.fixture(autouse=True)
    def setup(self, app_context):
        import inject

        from pkg.sqlalchemy import db
        from internal.model.dataset import Dataset
        from internal.model.document import Document
        from internal.model.keyword_table import KeywordTable
        from internal.model.process_rule import ProcessRule
        from internal.model.segment import Segment
        from internal.service.keyword_table_service import KeywordTableService
        from internal.service.document_status_service import DocumentStatusService

        self.db = db
        self.account_id = uuid.UUID("a666a888-8888-6666-1234-b9d69212aaaa")
        self.dataset_id = uuid.uuid4()
        self.vector_mock = MagicMock()

        with db.auto_commit():
            db.session.add(
                Dataset(
                    id=self.dataset_id,
                    account_id=self.account_id,
                    name=f"ops_test_ds_{self.dataset_id.hex[:8]}",
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

            self.doc = Document(
                account_id=self.account_id,
                dataset_id=self.dataset_id,
                upload_file_id=uuid.uuid4(),
                process_rule_id=pr.id,
                batch="2026101500000011112222",
                name="ops_doc.txt",
                position=1,
                status=DocumentStatus.COMPLETED,
                enabled=True,
            )
            db.session.add(self.doc)
            db.session.flush()

            self.segments = []
            seg_keywords = [["苹果", "价格"], ["苹果", "水果"]]
            for i, kws in enumerate(seg_keywords):
                seg = Segment(
                    account_id=self.account_id,
                    dataset_id=self.dataset_id,
                    document_id=self.doc.id,
                    node_id=str(uuid.uuid4()),
                    position=i,
                    content=f"内容{i}",
                    character_count=10,
                    keywords=kws,
                    status="completed",
                    enabled=True,
                )
                db.session.add(seg)
                self.segments.append(seg)

        # 词表按构建完成后的状态预置
        self.keyword_service = inject.instance(KeywordTableService)
        self.keyword_service.add_segments_keywords(
            self.dataset_id,
            {str(s.id): list(s.keywords) for s in self.segments},
        )

        self.service = DocumentStatusService(
            db=db,
            keyword_table_service=self.keyword_service,
            vector_store_service=self.vector_mock,
        )

        yield

        with db.auto_commit():
            db.session.execute(
                delete(Segment).where(Segment.document_id == self.doc.id)
            )
            db.session.execute(delete(Document).where(Document.id == self.doc.id))
            db.session.execute(
                delete(ProcessRule).where(ProcessRule.id == self.process_rule_id)
            )
            db.session.execute(
                delete(KeywordTable).where(KeywordTable.dataset_id == self.dataset_id)
            )
            db.session.execute(delete(Dataset).where(Dataset.id == self.dataset_id))

    def _refresh_doc(self):
        self.db.session.expire_all()
        return self.db.session.get(Document, self.doc.id)

    def _keyword_table(self):
        kt = self.keyword_service.get_or_create_by_dataset_id(self.dataset_id)
        self.db.session.refresh(kt)
        return dict(kt.keyword_table or {})

    # ── 禁用 ──────────────────────────────────────────────────────

    def test_disable_updates_document_and_segments(self):
        errors = self.service.disable_documents([str(self.doc.id)])
        assert errors == []
        doc = self._refresh_doc()
        assert doc.enabled is False
        assert doc.status == DocumentStatus.DISABLED
        assert doc.disabled_at is not None
        segs = self.db.session.execute(
            select(Segment).where(Segment.document_id == self.doc.id)
        ).scalars().all()
        assert all(seg.enabled is False for seg in segs)

    def test_disable_removes_keywords(self):
        self.service.disable_documents([str(self.doc.id)])
        # 该文档片段的所有关键词都应从词表移除
        assert self._keyword_table() == {}

    def test_disable_updates_vector_metadata(self):
        self.service.disable_documents([str(self.doc.id)])
        node_ids = [s.node_id for s in self.segments]
        self.vector_mock.update_documents_enabled.assert_called_once_with(
            node_ids, False
        )

    def test_disable_is_idempotent(self):
        self.service.disable_documents([str(self.doc.id)])
        errors = self.service.disable_documents([str(self.doc.id)])
        assert errors == []
        self.vector_mock.update_documents_enabled.assert_called_once()

    # ── 启用 ──────────────────────────────────────────────────────

    def test_enable_restores_everything(self):
        self.service.disable_documents([str(self.doc.id)])
        errors = self.service.enable_documents([str(self.doc.id)])
        assert errors == []
        doc = self._refresh_doc()
        assert doc.enabled is True
        assert doc.status == DocumentStatus.COMPLETED
        assert doc.disabled_at is None
        table = self._keyword_table()
        assert sorted(table.get("苹果", [])) == sorted(
            str(s.id) for s in self.segments
        )
        assert table.get("价格") == [str(self.segments[0].id)]
        assert table.get("水果") == [str(self.segments[1].id)]

    def test_enable_updates_vector_metadata_true(self):
        self.service.disable_documents([str(self.doc.id)])
        self.vector_mock.reset_mock()
        self.service.enable_documents([str(self.doc.id)])
        self.vector_mock.update_documents_enabled.assert_called_once_with(
            [s.node_id for s in self.segments], True
        )

    # ── 删除 ──────────────────────────────────────────────────────

    def test_delete_removes_all_relations(self):
        errors = self.service.delete_documents([str(self.doc.id)])
        assert errors == []
        self.db.session.expire_all()
        assert self.db.session.get(Document, self.doc.id) is None
        segs = self.db.session.execute(
            select(Segment).where(Segment.document_id == self.doc.id)
        ).scalars().all()
        assert segs == []
        assert self._keyword_table() == {}
        self.vector_mock.delete_segments.assert_called_once_with(
            [s.node_id for s in self.segments]
        )

    def test_delete_rejected_while_processing(self):
        with self.db.auto_commit():
            doc = self.db.session.get(Document, self.doc.id)
            doc.status = DocumentStatus.PARSING
        errors = self.service.delete_documents([str(self.doc.id)])
        assert len(errors) == 1
        assert "不能删除" in errors[0]
        # 文档与片段都还在，向量库没有被调用
        assert self.db.session.get(Document, self.doc.id) is not None
        self.vector_mock.delete_segments.assert_not_called()

    def test_delete_missing_document_reports_error(self):
        ghost = uuid.uuid4()
        errors = self.service.delete_documents([str(ghost)])
        assert len(errors) == 1
        assert "不存在" in errors[0]
