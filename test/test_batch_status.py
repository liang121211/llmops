import uuid

import pytest

from internal.entity import DocumentStatus, SegmentStatus
from internal.pkg.response.http_code import HttpCode


class TestBatchStatusAPI:
    """文档批处理状态接口测试。"""

    @pytest.fixture(autouse=True)
    def setup(self, client, app_context):
        self.client = client
        from pkg.sqlalchemy import db
        from internal.model.document import Document
        from internal.model.process_rule import ProcessRule
        from internal.model.segment import Segment
        from internal.model.upload_file import UploadFile
        from internal.model.dataset import Dataset

        self.db = db
        account_id = uuid.UUID("a666a888-8888-6666-1234-b9d69212aaaa")
        self.dataset_id = uuid.uuid4()
        self.batch = "2026101412000012345678"

        with db.auto_commit():
            ds = Dataset(
                id=self.dataset_id,
                account_id=account_id,
                name="batch_test_ds",
                description="test",
            )
            db.session.add(ds)

        with db.auto_commit():
            pr = ProcessRule(
                account_id=account_id,
                dataset_id=self.dataset_id,
                mode="automatic",
                rule={},
            )
            db.session.add(pr)
            self.process_rule = pr

        self.docs = []
        self.segments = []
        with db.auto_commit():
            for i in range(3):
                uf = UploadFile(
                    account_id=account_id,
                    name=f"file_{i}.txt",
                    key=f"test/file_{i}.txt",
                    size=100 * (i + 1),
                    extension="txt",
                    mime_type="text/plain",
                    hash=f"hash_{i}",
                )
                db.session.add(uf)
                db.session.flush()

                doc = Document(
                    account_id=account_id,
                    dataset_id=self.dataset_id,
                    upload_file_id=uf.id,
                    process_rule_id=pr.id,
                    batch=self.batch,
                    name=f"file_{i}.txt",
                    position=i + 1,
                    status=DocumentStatus.COMPLETED,
                    processing_started_at=None,
                    parsing_completed_at=None,
                    splitting_completed_at=None,
                )
                db.session.add(doc)
                db.session.flush()
                self.docs.append(doc)

                for j in range(2):
                    seg = Segment(
                        account_id=account_id,
                        dataset_id=self.dataset_id,
                        document_id=doc.id,
                        node_id=f"node_{i}_{j}",
                        position=j,
                        content=f"内容 {i}-{j}",
                        character_count=10,
                        status=SegmentStatus.COMPLETED if j == 0 else SegmentStatus.WAITING,
                    )
                    db.session.add(seg)
                    self.segments.append(seg)

        yield

        from sqlalchemy import delete as sa_delete

        with db.auto_commit():
            db.session.execute(sa_delete(Segment).where(Segment.id.in_([s.id for s in self.segments])))
            db.session.execute(sa_delete(Document).where(Document.id.in_([d.id for d in self.docs])))
            db.session.execute(sa_delete(ProcessRule).where(ProcessRule.id == pr.id))
            db.session.execute(sa_delete(Dataset).where(Dataset.id == self.dataset_id))
            db.session.execute(sa_delete(UploadFile).where(UploadFile.account_id == account_id, UploadFile.key.like("test/file_%")))

    def test_get_batch_status_success(self):
        url = f"/datasets/{self.dataset_id}/documents/batch/{self.batch}"
        resp = self.client.get(url)
        body = resp.get_json()
        assert body["code"] == HttpCode.SUCCESS.value
        data = body["data"]
        assert isinstance(data, list)
        assert len(data) == 3

    def test_batch_status_fields(self):
        url = f"/datasets/{self.dataset_id}/documents/batch/{self.batch}"
        resp = self.client.get(url)
        body = resp.get_json()
        item = body["data"][0]
        assert "id" in item
        assert "name" in item
        assert "extension" in item
        assert "mime_type" in item
        assert "size" in item
        assert "created_at" in item
        assert "position" in item
        assert "segment_count" in item
        assert "status" in item
        assert "error" in item
        assert "completed_segment_count" in item

    def test_batch_status_segment_counts(self):
        url = f"/datasets/{self.dataset_id}/documents/batch/{self.batch}"
        resp = self.client.get(url)
        body = resp.get_json()
        for item in body["data"]:
            assert item["segment_count"] == 2
            assert item["completed_segment_count"] == 1

    def test_batch_status_order_by_position(self):
        url = f"/datasets/{self.dataset_id}/documents/batch/{self.batch}"
        resp = self.client.get(url)
        body = resp.get_json()
        positions = [item["position"] for item in body["data"]]
        assert positions == sorted(positions)

    def test_batch_status_nonexistent_dataset(self):
        fake_id = uuid.uuid4()
        url = f"/datasets/{fake_id}/documents/batch/{self.batch}"
        resp = self.client.get(url)
        body = resp.get_json()
        assert body["code"] != HttpCode.SUCCESS.value

    def test_batch_status_empty_batch(self):
        url = f"/datasets/{self.dataset_id}/documents/batch/nonexistent_batch"
        resp = self.client.get(url)
        body = resp.get_json()
        assert body["code"] == HttpCode.SUCCESS.value
        assert body["data"] == []
