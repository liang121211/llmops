import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy import delete as sa_delete

from internal.entity import DocumentStatus, SegmentStatus
from internal.model.dataset import Dataset
from internal.model.document import Document
from internal.model.keyword_table import KeywordTable
from internal.model.process_rule import ProcessRule
from internal.model.segment import Segment
from internal.pkg.response.http_code import HttpCode


class TestSegmentAPI:
    """片段接口测试：路由、校验与响应结构；向量操作以 mock 替换。"""

    @pytest.fixture(autouse=True)
    def setup(self, client, app_context, monkeypatch):
        from app.http.app import app
        from pkg.sqlalchemy import db

        self.client = client
        self.db = db
        self.account_id = uuid.UUID("a666a888-8888-6666-1234-b9d69212aaaa")
        self.dataset_id = uuid.uuid4()
        self.vector_mock = MagicMock()

        # 路由挂的是导入期创建的 handler 实例，直接替换其片段服务的向量依赖
        handler = app.view_functions["app.get_segment"].__self__
        monkeypatch.setattr(
            handler.segment_service, "vector_store_service", self.vector_mock
        )

        with db.auto_commit():
            db.session.add(
                Dataset(
                    id=self.dataset_id,
                    account_id=self.account_id,
                    name=f"seg_api_ds_{self.dataset_id.hex[:8]}",
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
                batch="2026101500000099990000",
                name="seg_api.txt",
                position=1,
                status=DocumentStatus.COMPLETED,
                enabled=True,
            )
            db.session.add(self.doc)
            db.session.flush()
            self.segments = []
            for i, kws in enumerate([["苹果"], ["水果"]]):
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

        yield

        with db.auto_commit():
            db.session.execute(
                sa_delete(Segment).where(Segment.document_id == self.doc.id)
            )
            db.session.execute(sa_delete(Document).where(Document.id == self.doc.id))
            db.session.execute(
                sa_delete(ProcessRule).where(ProcessRule.id == self.process_rule_id)
            )
            db.session.execute(
                sa_delete(KeywordTable).where(
                    KeywordTable.dataset_id == self.dataset_id
                )
            )
            db.session.execute(sa_delete(Dataset).where(Dataset.id == self.dataset_id))

    def base_url(self):
        return f"/datasets/{self.dataset_id}/documents/{self.doc.id}/segments"

    def _set_doc_status(self, status):
        with self.db.auto_commit():
            doc = self.db.session.get(Document, self.doc.id)
            doc.status = status

    # ── 查询 ──────────────────────────────────────────────────────

    def test_list_segments(self):
        body = self.client.get(f"{self.base_url()}?current_page=1&page_size=10").get_json()
        assert body["code"] == HttpCode.SUCCESS.value
        assert len(body["data"]["segments"]) == 2
        assert body["data"]["paginator"]["total_record"] == 2

    def test_get_single_segment(self):
        seg_id = str(self.segments[0].id)
        body = self.client.get(f"{self.base_url()}/{seg_id}").get_json()
        assert body["code"] == HttpCode.SUCCESS.value
        assert body["data"]["segment"]["id"] == seg_id

    def test_get_segment_wrong_dataset(self):
        fake_ds = uuid.uuid4()
        body = self.client.get(
            f"/datasets/{fake_ds}/documents/{self.doc.id}/segments/{self.segments[0].id}"
        ).get_json()
        assert body["code"] == HttpCode.NOT_FOUND.value

    def test_list_segments_document_not_found(self):
        body = self.client.get(
            f"/datasets/{self.dataset_id}/documents/{uuid.uuid4()}/segments"
        ).get_json()
        assert body["code"] == HttpCode.NOT_FOUND.value

    # ── 禁用 / 启用 ───────────────────────────────────────────────

    def test_disable_and_enable_segment(self):
        seg_id = str(self.segments[0].id)
        body = self.client.put(f"{self.base_url()}/{seg_id}/disable").get_json()
        assert body["code"] == HttpCode.SUCCESS.value
        assert body["data"]["segment"]["enabled"] is False
        self.vector_mock.update_segments_enabled.assert_called_once_with(
            [self.segments[0].node_id], False
        )

        self.vector_mock.reset_mock()
        body = self.client.put(f"{self.base_url()}/{seg_id}/enable").get_json()
        assert body["code"] == HttpCode.SUCCESS.value
        assert body["data"]["segment"]["enabled"] is True
        self.vector_mock.update_segments_enabled.assert_called_once_with(
            [self.segments[0].node_id], True
        )

    def test_disable_twice_returns_fail(self):
        seg_id = str(self.segments[0].id)
        assert self.client.put(f"{self.base_url()}/{seg_id}/disable").get_json()[
            "code"
        ] == HttpCode.SUCCESS.value
        body = self.client.put(f"{self.base_url()}/{seg_id}/disable").get_json()
        assert body["code"] == HttpCode.FAIL.value
        assert "已处于禁用状态" in body["message"]

    def test_enable_not_found_segment(self):
        body = self.client.put(
            f"{self.base_url()}/{uuid.uuid4()}/enable"
        ).get_json()
        assert body["code"] == HttpCode.NOT_FOUND.value

    def test_segment_ops_rejected_while_document_processing(self):
        self._set_doc_status(DocumentStatus.INDEXING)
        seg_id = str(self.segments[0].id)
        body = self.client.put(f"{self.base_url()}/{seg_id}/disable").get_json()
        assert body["code"] == HttpCode.FAIL.value
        assert "处理中" in body["message"]
        body = self.client.post(
            self.base_url(), json={"content": "x", "keywords": []}
        ).get_json()
        assert body["code"] == HttpCode.FAIL.value

    # ── 新增 ──────────────────────────────────────────────────────

    def test_create_segment(self):
        body = self.client.post(
            self.base_url(),
            json={"content": "手动新增的片段内容", "keywords": ["手动", "新增"]},
        ).get_json()
        assert body["code"] == HttpCode.SUCCESS.value
        segment = body["data"]["segment"]
        assert segment["position"] == 2
        assert segment["content"] == "手动新增的片段内容"
        self.vector_mock.upsert_segment.assert_called_once()

    def test_create_segment_missing_content(self):
        body = self.client.post(self.base_url(), json={"keywords": []}).get_json()
        assert body["code"] == HttpCode.VALIDATE_ERROR.value

    def test_create_segment_bad_keywords_type(self):
        body = self.client.post(
            self.base_url(), json={"content": "内容", "keywords": "不是列表"}
        ).get_json()
        assert body["code"] == HttpCode.FAIL.value

    # ── 修改 ──────────────────────────────────────────────────────

    def test_update_segment(self):
        seg_id = str(self.segments[0].id)
        body = self.client.put(
            f"{self.base_url()}/{seg_id}",
            json={"content": "修改后的内容", "keywords": ["修改"]},
        ).get_json()
        assert body["code"] == HttpCode.SUCCESS.value
        assert body["data"]["segment"]["content"] == "修改后的内容"
        self.vector_mock.upsert_segment.assert_called_once()

    def test_update_segment_requires_keywords(self):
        seg_id = str(self.segments[0].id)
        body = self.client.put(
            f"{self.base_url()}/{seg_id}", json={"content": "只有内容"}
        ).get_json()
        assert body["code"] == HttpCode.FAIL.value
        assert "keywords" in body["message"]

    # ── 删除 ──────────────────────────────────────────────────────

    def test_delete_segment(self):
        seg_id = str(self.segments[0].id)
        body = self.client.delete(f"{self.base_url()}/{seg_id}").get_json()
        assert body["code"] == HttpCode.SUCCESS.value
        assert body["data"]["id"] == seg_id
        self.vector_mock.delete_segments.assert_called_once_with(
            [self.segments[0].node_id]
        )

    def test_delete_segment_not_found(self):
        body = self.client.delete(f"{self.base_url()}/{uuid.uuid4()}").get_json()
        assert body["code"] == HttpCode.NOT_FOUND.value


__all__ = ["TestSegmentAPI"]
