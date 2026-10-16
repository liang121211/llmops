import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy import delete, select
from werkzeug.datastructures import MultiDict

from internal.entity import DocumentStatus, SegmentStatus
from internal.model.dataset import Dataset
from internal.model.document import Document
from internal.model.keyword_table import KeywordTable
from internal.model.process_rule import ProcessRule
from internal.model.segment import Segment
from internal.schema.segment_schema import SegmentListReq


class TestSegmentService:
    """片段服务测试，向量库操作以 mock 替代（本地 Weaviate 未启动）。"""

    @pytest.fixture(autouse=True)
    def setup(self, app_context):
        import inject

        from pkg.sqlalchemy import db

        from internal.service.keyword_table_service import KeywordTableService
        from internal.service.segment_service import SegmentService

        self.db = db
        self.account_id = uuid.UUID("a666a888-8888-6666-1234-b9d69212aaaa")
        self.dataset_id = uuid.uuid4()
        self.vector_mock = MagicMock()

        with db.auto_commit():
            db.session.add(
                Dataset(
                    id=self.dataset_id,
                    account_id=self.account_id,
                    name=f"seg_test_ds_{self.dataset_id.hex[:8]}",
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
                batch="2026101500000077778888",
                name="seg_doc.txt",
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
                    status=SegmentStatus.COMPLETED,
                    enabled=True,
                )
                db.session.add(seg)
                self.segments.append(seg)

        self.keyword_service = inject.instance(KeywordTableService)
        self.keyword_service.add_segments_keywords(
            self.dataset_id,
            {str(s.id): list(s.keywords) for s in self.segments},
        )

        self.service = SegmentService(
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

    # ── 查询 ──────────────────────────────────────────────────────

    def test_get_segment_in_dataset_ok(self):
        seg = self.segments[0]
        got = self.service.get_segment_in_dataset(
            self.dataset_id, self.doc.id, seg.id
        )
        assert got is not None
        assert got.id == seg.id

    def test_get_segment_wrong_document_returns_none(self):
        got = self.service.get_segment_in_dataset(
            self.dataset_id, uuid.uuid4(), self.segments[0].id
        )
        assert got is None

    def test_get_segment_wrong_dataset_returns_none(self):
        got = self.service.get_segment_in_dataset(
            uuid.uuid4(), self.doc.id, self.segments[0].id
        )
        assert got is None

    def test_get_segments_with_page(self):
        req = SegmentListReq(formdata=MultiDict({"current_page": 1, "page_size": 1}))
        result = self.service.get_segments_with_page(req, self.dataset_id, self.doc.id)
        assert len(result["list"]) == 1
        assert result["list"][0].position == 0
        assert result["paginator"]["total_record"] == 2

    # ── 禁用 / 启用 ───────────────────────────────────────────────

    def _keyword_table(self):
        kt = self.keyword_service.get_or_create_by_dataset_id(self.dataset_id)
        self.db.session.refresh(kt)
        return dict(kt.keyword_table or {})

    def _refresh_segment(self, seg):
        self.db.session.expire_all()
        return self.db.session.get(Segment, seg.id)

    def test_disable_removes_keywords_and_updates_vector(self):
        seg = self.segments[0]
        result = self.service.disable_segment(self.dataset_id, self.doc.id, seg.id)
        assert result.enabled is False
        refreshed = self._refresh_segment(seg)
        assert refreshed.enabled is False
        assert refreshed.disabled_at is not None
        # 片段0 的关键词从词表移除，片段1 的引用保留
        table = self._keyword_table()
        assert table.get("价格") is None
        assert table.get("苹果") == [str(self.segments[1].id)]
        self.vector_mock.update_segments_enabled.assert_called_once_with(
            [seg.node_id], False
        )

    def test_disable_already_disabled_raises(self):
        seg = self.segments[0]
        self.service.disable_segment(self.dataset_id, self.doc.id, seg.id)
        with pytest.raises(ValueError, match="已处于禁用状态"):
            self.service.disable_segment(self.dataset_id, self.doc.id, seg.id)

    def test_enable_restores_keywords_and_vector(self):
        seg = self.segments[0]
        self.service.disable_segment(self.dataset_id, self.doc.id, seg.id)
        self.vector_mock.reset_mock()
        self.service.enable_segment(self.dataset_id, self.doc.id, seg.id)
        refreshed = self._refresh_segment(seg)
        assert refreshed.enabled is True
        assert refreshed.disabled_at is None
        table = self._keyword_table()
        assert sorted(table.get("苹果", [])) == sorted(
            str(s.id) for s in self.segments
        )
        assert table.get("价格") == [str(seg.id)]
        self.vector_mock.update_segments_enabled.assert_called_once_with(
            [seg.node_id], True
        )

    def test_enable_already_enabled_raises(self):
        seg = self.segments[0]
        with pytest.raises(ValueError, match="已处于启用状态"):
            self.service.enable_segment(self.dataset_id, self.doc.id, seg.id)

    def test_enable_skips_keywords_when_document_disabled(self):
        seg = self.segments[0]
        self.service.disable_segment(self.dataset_id, self.doc.id, seg.id)
        # 文档处于禁用状态时启用片段，词表不应回填
        with self.db.auto_commit():
            doc = self.db.session.get(Document, self.doc.id)
            doc.enabled = False
        self.service.enable_segment(self.dataset_id, self.doc.id, seg.id)
        assert self._refresh_segment(seg).enabled is True
        table = self._keyword_table()
        assert str(seg.id) not in table.get("苹果", [])

    # ── 新增 ──────────────────────────────────────────────────────

    def _make_segment(self, content="新片段内容", keywords=("新", "关键词")):
        doc = self.db.session.get(Document, self.doc.id)
        return self.service.create_segment(doc, content, list(keywords))

    def test_create_appends_segment_with_keywords_and_vector(self):
        seg = self._make_segment()
        assert seg.position == 2
        assert seg.enabled is True
        assert seg.status == SegmentStatus.COMPLETED
        assert seg.character_count == len("新片段内容")
        refreshed = self._refresh_segment(seg)
        assert refreshed.keywords == ["新", "关键词"]
        table = self._keyword_table()
        assert table.get("新") == [str(seg.id)]
        self.vector_mock.upsert_segment.assert_called_once()
        args = self.vector_mock.upsert_segment.call_args.args
        assert args[0] == seg.node_id
        assert args[2]["segment_enabled"] is True
        assert args[2]["document_enabled"] is True

    def test_create_rolls_back_when_vector_write_fails(self):
        self.vector_mock.upsert_segment.side_effect = RuntimeError("向量库不可用")
        with pytest.raises(RuntimeError):
            self._make_segment()
        self.vector_mock.upsert_segment.side_effect = None
        segs = self.db.session.execute(
            select(Segment).where(Segment.document_id == self.doc.id)
        ).scalars().all()
        assert len(segs) == 2
        table = self._keyword_table()
        assert "新" not in table

    # ── 修改 ──────────────────────────────────────────────────────

    def test_update_replaces_content_and_keywords(self):
        seg = self.segments[0]
        result = self.service.update_segment(
            self.dataset_id, self.doc.id, seg.id, "更新后的内容", ["更新"]
        )
        assert result.content == "更新后的内容"
        refreshed = self._refresh_segment(seg)
        assert refreshed.keywords == ["更新"]
        assert refreshed.character_count == len("更新后的内容")
        table = self._keyword_table()
        # 旧关键词整组替换
        assert "价格" not in table
        assert str(seg.id) not in table.get("苹果", [])
        assert table.get("更新") == [str(seg.id)]
        self.vector_mock.upsert_segment.assert_called_once()

    def test_update_keeps_disabled_segment_out_of_keyword_table(self):
        seg = self.segments[0]
        self.service.disable_segment(self.dataset_id, self.doc.id, seg.id)
        self.vector_mock.reset_mock()
        self.service.update_segment(
            self.dataset_id, self.doc.id, seg.id, "禁用中修改", ["新词"]
        )
        refreshed = self._refresh_segment(seg)
        assert refreshed.content == "禁用中修改"
        table = self._keyword_table()
        # 禁用片段更新后词表依然不含其引用
        assert "新词" not in table
        # 向量内容仍被刷新，属性保持禁用
        props = self.vector_mock.upsert_segment.call_args.args[2]
        assert props["segment_enabled"] is False

    def test_update_missing_segment_raises(self):
        with pytest.raises(ValueError, match="不存在"):
            self.service.update_segment(
                self.dataset_id, self.doc.id, uuid.uuid4(), "x", []
            )

    # ── 删除 ──────────────────────────────────────────────────────

    def test_delete_removes_vector_keywords_and_row(self):
        seg = self.segments[0]
        self.service.delete_segment(self.dataset_id, self.doc.id, seg.id)
        self.db.session.expire_all()
        assert self.db.session.get(Segment, seg.id) is None
        table = self._keyword_table()
        assert "价格" not in table
        assert table.get("苹果") == [str(self.segments[1].id)]
        self.vector_mock.delete_segments.assert_called_once_with([seg.node_id])

    def test_delete_missing_segment_raises(self):
        with pytest.raises(ValueError, match="不存在"):
            self.service.delete_segment(
                self.dataset_id, self.doc.id, uuid.uuid4()
            )


__all__ = ["TestSegmentService"]
