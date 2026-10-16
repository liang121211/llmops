import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy import delete as sa_delete

from internal.entity import DocumentStatus, SegmentStatus
from internal.model.keyword_table import KeywordTable


class TestDocumentModelProperties:
    """Document 模型属性函数测试。"""

    @pytest.fixture(autouse=True)
    def setup(self, app_context):
        from pkg.sqlalchemy import db
        from internal.model.document import Document
        from internal.model.process_rule import ProcessRule
        from internal.model.segment import Segment
        from internal.model.upload_file import UploadFile
        import uuid

        self.db = db
        self.Document = Document
        self.ProcessRule = ProcessRule
        self.Segment = Segment
        self.UploadFile = UploadFile

        account_id = uuid.UUID("a666a888-8888-6666-1234-b9d69212aaaa")
        dataset_id = uuid.uuid4()

        with db.auto_commit():
            uf = UploadFile(
                account_id=account_id,
                name="test.txt",
                key="test/test.txt",
                size=100,
                extension="txt",
                mime_type="text/plain",
                hash="abc123",
            )
            db.session.add(uf)
            self.upload_file = uf

        with db.auto_commit():
            pr = ProcessRule(
                account_id=account_id,
                dataset_id=dataset_id,
                mode="automatic",
                rule={"segment": {"chunk_size": 500}},
            )
            db.session.add(pr)
            self.process_rule = pr

        with db.auto_commit():
            doc = Document(
                account_id=account_id,
                dataset_id=dataset_id,
                upload_file_id=uf.id,
                process_rule_id=pr.id,
                batch="test_batch",
                name="test.txt",
                position=1,
                status=DocumentStatus.WAITING,
            )
            db.session.add(doc)
            self.doc = doc

        with db.auto_commit():
            for i in range(3):
                seg = Segment(
                    account_id=account_id,
                    dataset_id=dataset_id,
                    document_id=doc.id,
                    node_id=f"node_{i}",
                    position=i,
                    content=f"内容片段 {i}",
                    character_count=10,
                    hit_count=i * 5,
                    status=SegmentStatus.COMPLETED,
                )
                db.session.add(seg)

        self._account_id = account_id
        self._dataset_id = dataset_id

        yield

        with db.auto_commit():
            db.session.execute(
                db.session.query(Segment).filter(
                    Segment.document_id == self.doc.id
                ).delete.__func__(
                    db.session.query(Segment).filter(
                        Segment.document_id == self.doc.id
                    )
                ) if False else __import__("sqlalchemy").delete(Segment).where(
                    Segment.document_id == self.doc.id
                )
            )

    def test_upload_file_property(self, app_context):
        uf = self.doc.upload_file
        assert uf is not None
        assert uf.name == "test.txt"

    def test_process_rule_property(self, app_context):
        pr = self.doc.process_rule
        assert pr is not None
        assert pr.mode == "automatic"

    def test_segment_count(self, app_context):
        assert self.doc.segment_count == 3

    def test_hit_count(self, app_context):
        # 0 + 5 + 10 = 15
        assert self.doc.hit_count == 15


class TestStatusEntities:
    """状态枚举常量测试。"""

    def test_document_status_values(self):
        assert DocumentStatus.WAITING == "waiting"
        assert DocumentStatus.PARSING == "parsing"
        assert DocumentStatus.SPLITTING == "splitting"
        assert DocumentStatus.INDEXING == "indexing"
        assert DocumentStatus.COMPLETED == "completed"
        assert DocumentStatus.ERROR == "error"

    def test_segment_status_values(self):
        assert SegmentStatus.WAITING == "waiting"
        assert SegmentStatus.PROCESSING == "processing"
        assert SegmentStatus.COMPLETED == "completed"
        assert SegmentStatus.ERROR == "error"


class TestRebuildCleanup:
    """重建前 _cleanup_old_segments 应清理旧片段的向量、词表引用与 DB 行。"""

    @pytest.fixture(autouse=True)
    def setup(self, app_context):
        import inject

        from internal.model.document import Document
        from internal.model.keyword_table import KeywordTable
        from internal.model.process_rule import ProcessRule
        from internal.model.segment import Segment
        from internal.model.upload_file import UploadFile
        from internal.service.index_build_service import IndexBuildService
        from internal.service.keyword_table_service import KeywordTableService
        from pkg.sqlalchemy import db

        self.db = db
        self.Segment = Segment
        account_id = uuid.UUID("a666a888-8888-6666-1234-b9d69212aaaa")
        dataset_id = uuid.uuid4()

        with db.auto_commit():
            uf = UploadFile(
                account_id=account_id, name="t.txt", key="t/t.txt", size=1,
                extension="txt", mime_type="text/plain", hash="h1",
            )
            pr = ProcessRule(
                account_id=account_id, dataset_id=dataset_id,
                mode="automatic", rule={"segment": {"chunk_size": 500}},
            )
            db.session.add_all([uf, pr])
            db.session.flush()
            doc = Document(
                account_id=account_id, dataset_id=dataset_id,
                upload_file_id=uf.id, process_rule_id=pr.id,
                batch="b1", name="t.txt", position=1,
                status=DocumentStatus.ERROR,
            )
            db.session.add(doc)
            db.session.flush()
            seg_a = Segment(
                account_id=account_id, dataset_id=dataset_id, document_id=doc.id,
                node_id="node-a", position=0, content="旧片段A",
                character_count=3, status=SegmentStatus.COMPLETED,
            )
            seg_b = Segment(
                account_id=account_id, dataset_id=dataset_id, document_id=doc.id,
                node_id="node-b", position=1, content="旧片段B",
                character_count=3, status=SegmentStatus.COMPLETED,
            )
            db.session.add_all([seg_a, seg_b])
            db.session.flush()
            self.doc, self.seg_a, self.seg_b = doc, seg_a, seg_b

        self.kt_service = inject.instance(KeywordTableService)
        self.kt_service.add_segments_keywords(dataset_id, {
            str(seg_a.id): ["牛肉丸", "手工"],
            str(seg_b.id): ["手工"],
        })

        self.vector_mock = MagicMock()
        # autoparams 包装类需显式传全部字段构造
        self.service = IndexBuildService(
            db=db,
            file_loader=MagicMock(),
            process_rule_service=MagicMock(),
            keyword_table_service=self.kt_service,
            embedding_service=MagicMock(),
            vector_store_service=self.vector_mock,
        )
        self._dataset_id = dataset_id

        yield

        with db.auto_commit():
            db.session.execute(sa_delete(Segment).where(Segment.document_id == doc.id))
            db.session.execute(sa_delete(Document).where(Document.id == doc.id))
            db.session.execute(sa_delete(ProcessRule).where(ProcessRule.dataset_id == dataset_id))
            db.session.execute(sa_delete(UploadFile).where(UploadFile.id == uf.id))
            db.session.execute(sa_delete(KeywordTable).where(KeywordTable.dataset_id == dataset_id))

    def _keyword_table(self) -> dict:
        kt = self.db.session.query(KeywordTable).filter_by(
            dataset_id=self._dataset_id
        ).first()
        return dict(kt.keyword_table or {}) if kt else {}

    def test_cleanup_removes_segments_rows(self):
        self.service._cleanup_old_segments(self.doc)

        left = self.db.session.query(self.Segment).filter(
            self.Segment.document_id == self.doc.id
        ).count()
        assert left == 0

    def test_cleanup_deletes_vectors(self):
        self.service._cleanup_old_segments(self.doc)

        called = self.vector_mock.delete_segments.call_args.args[0]
        assert sorted(called) == ["node-a", "node-b"]

    def test_cleanup_removes_keyword_references(self):
        assert "手工" in self._keyword_table()

        self.service._cleanup_old_segments(self.doc)

        table = self._keyword_table()
        # 旧片段全部移除后，只被它们引用的关键词应整体删除
        assert table == {}

    def test_cleanup_noop_without_old_segments(self):
        self.service._cleanup_old_segments(self.doc)
        self.vector_mock.delete_segments.reset_mock()

        # 第二次清理已无旧片段：不应触碰向量库与词表
        self.service._cleanup_old_segments(self.doc)
        self.vector_mock.delete_segments.assert_not_called()
