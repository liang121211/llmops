import uuid

import pytest

from internal.entity import DocumentStatus
from internal.pkg.response.http_code import HttpCode


class TestDocumentQueryAPI:
    """文档查询、分页查询与修改标题接口测试。"""

    @pytest.fixture(autouse=True)
    def setup(self, client, app_context):
        self.client = client
        from pkg.sqlalchemy import db
        from internal.model.document import Document
        from internal.model.process_rule import ProcessRule
        from internal.model.upload_file import UploadFile
        from internal.model.dataset import Dataset

        self.db = db
        self.account_id = uuid.UUID("a666a888-8888-6666-1234-b9d69212aaaa")
        self.dataset_id = uuid.uuid4()
        self.other_dataset_id = uuid.uuid4()

        with db.auto_commit():
            for ds_id in (self.dataset_id, self.other_dataset_id):
                db.session.add(
                    Dataset(
                        id=ds_id,
                        account_id=self.account_id,
                        name=f"query_test_ds_{ds_id.hex[:8]}",
                        description="test",
                    )
                )

        with db.auto_commit():
            pr = ProcessRule(
                account_id=self.account_id,
                dataset_id=self.dataset_id,
                mode="automatic",
                rule={},
            )
            db.session.add(pr)
            db.session.flush()
            self.process_rule_id = pr.id

        self.docs = []
        self.upload_file_ids = []
        with db.auto_commit():
            for i in range(3):
                uf = UploadFile(
                    account_id=self.account_id,
                    name=f"query_{i}.txt",
                    key=f"test/query_{i}.txt",
                    size=100 * (i + 1),
                    extension="txt",
                    mime_type="text/plain",
                    hash=f"query_hash_{i}",
                )
                db.session.add(uf)
                db.session.flush()
                self.upload_file_ids.append(uf.id)

                doc = Document(
                    account_id=self.account_id,
                    dataset_id=self.dataset_id,
                    upload_file_id=uf.id,
                    process_rule_id=self.process_rule_id,
                    batch="2026101500000012345678",
                    name=f"query_{i}.txt",
                    position=i + 1,
                    status=DocumentStatus.COMPLETED,
                )
                db.session.add(doc)
                db.session.flush()
                self.docs.append(doc)

        # 另一知识库下的文档，用于验证跨库访问被视为不存在
        with db.auto_commit():
            other_uf = UploadFile(
                account_id=self.account_id,
                name="other.txt",
                key="test/query_other.txt",
                size=1,
                extension="txt",
                mime_type="text/plain",
                hash="query_hash_other",
            )
            db.session.add(other_uf)
            db.session.flush()
            self.upload_file_ids.append(other_uf.id)
            other_doc = Document(
                account_id=self.account_id,
                dataset_id=self.other_dataset_id,
                upload_file_id=other_uf.id,
                process_rule_id=self.process_rule_id,
                batch="2026101500000087654321",
                name="other.txt",
                position=1,
                status=DocumentStatus.COMPLETED,
            )
            db.session.add(other_doc)
            db.session.flush()
            self.other_doc_id = other_doc.id

        yield

        from sqlalchemy import delete as sa_delete
        from internal.model.segment import Segment

        doc_ids = [d.id for d in self.docs] + [self.other_doc_id]
        with db.auto_commit():
            db.session.execute(sa_delete(Segment).where(Segment.document_id.in_(doc_ids)))
            db.session.execute(sa_delete(Document).where(Document.id.in_(doc_ids)))
            db.session.execute(
                sa_delete(ProcessRule).where(ProcessRule.id == self.process_rule_id)
            )
            db.session.execute(
                sa_delete(UploadFile).where(UploadFile.id.in_(self.upload_file_ids))
            )
            db.session.execute(
                sa_delete(Dataset).where(
                    Dataset.id.in_([self.dataset_id, self.other_dataset_id])
                )
            )

    # ── 根据 ID 查询文档 ──────────────────────────────────────────

    def test_get_document_success(self):
        doc_id = self.docs[0].id
        resp = self.client.get(f"/datasets/{self.dataset_id}/documents/{doc_id}")
        body = resp.get_json()
        assert body["code"] == HttpCode.SUCCESS.value
        document = body["data"]["document"]
        assert document["id"] == str(doc_id)
        assert document["name"] == "query_0.txt"
        assert document["dataset_id"] == str(self.dataset_id)

    def test_get_document_not_found(self):
        fake_id = uuid.uuid4()
        resp = self.client.get(f"/datasets/{self.dataset_id}/documents/{fake_id}")
        body = resp.get_json()
        assert body["code"] == HttpCode.NOT_FOUND.value

    def test_get_document_wrong_dataset(self):
        # 文档存在但不属于该知识库，应视为不存在
        resp = self.client.get(
            f"/datasets/{self.dataset_id}/documents/{self.other_doc_id}"
        )
        body = resp.get_json()
        assert body["code"] == HttpCode.NOT_FOUND.value

    # ── 分页查询文档 ──────────────────────────────────────────────

    def test_get_documents_default_page(self):
        resp = self.client.get(f"/datasets/{self.dataset_id}/documents")
        body = resp.get_json()
        assert body["code"] == HttpCode.SUCCESS.value
        data = body["data"]
        assert len(data["documents"]) == 3
        positions = [item["position"] for item in data["documents"]]
        assert positions == [1, 2, 3]
        paginator = data["paginator"]
        assert paginator["total_record"] == 3
        assert paginator["total_page"] == 1
        assert paginator["current_page"] == 1
        assert paginator["page_size"] == 20

    def test_get_documents_custom_page_size(self):
        resp = self.client.get(
            f"/datasets/{self.dataset_id}/documents?page_size=2&current_page=1"
        )
        body = resp.get_json()
        assert body["code"] == HttpCode.SUCCESS.value
        assert len(body["data"]["documents"]) == 2
        assert body["data"]["paginator"]["total_page"] == 2

        resp2 = self.client.get(
            f"/datasets/{self.dataset_id}/documents?page_size=2&current_page=2"
        )
        body2 = resp2.get_json()
        assert len(body2["data"]["documents"]) == 1
        assert body2["data"]["documents"][0]["position"] == 3

    def test_get_documents_invalid_page_size(self):
        resp = self.client.get(
            f"/datasets/{self.dataset_id}/documents?page_size=200"
        )
        body = resp.get_json()
        assert body["code"] == HttpCode.VALIDATE_ERROR.value

    def test_get_documents_nonexistent_dataset(self):
        fake_id = uuid.uuid4()
        resp = self.client.get(f"/datasets/{fake_id}/documents")
        body = resp.get_json()
        assert body["code"] == HttpCode.NOT_FOUND.value

    def test_get_documents_other_dataset(self):
        resp = self.client.get(f"/datasets/{self.other_dataset_id}/documents")
        body = resp.get_json()
        # 每个知识库的列表只包含自己的文档
        assert body["code"] == HttpCode.SUCCESS.value
        assert body["data"]["paginator"]["total_record"] == 1
        assert body["data"]["documents"][0]["name"] == "other.txt"

    # ── 修改文档标题 ──────────────────────────────────────────────

    def test_update_document_name(self):
        doc_id = self.docs[0].id
        resp = self.client.put(
            f"/datasets/{self.dataset_id}/documents/{doc_id}",
            json={"name": "重命名标题"},
        )
        body = resp.get_json()
        assert body["code"] == HttpCode.SUCCESS.value
        assert body["data"]["document"]["name"] == "重命名标题"

    def test_update_document_name_persisted(self):
        doc_id = self.docs[1].id
        self.client.put(
            f"/datasets/{self.dataset_id}/documents/{doc_id}",
            json={"name": "新标题"},
        )
        get_body = self.client.get(
            f"/datasets/{self.dataset_id}/documents/{doc_id}"
        ).get_json()
        assert get_body["data"]["document"]["name"] == "新标题"

    def test_update_document_missing_name(self):
        doc_id = self.docs[0].id
        resp = self.client.put(
            f"/datasets/{self.dataset_id}/documents/{doc_id}", json={}
        )
        body = resp.get_json()
        assert body["code"] == HttpCode.VALIDATE_ERROR.value

    def test_update_document_name_too_long(self):
        doc_id = self.docs[0].id
        resp = self.client.put(
            f"/datasets/{self.dataset_id}/documents/{doc_id}",
            json={"name": "x" * 256},
        )
        body = resp.get_json()
        assert body["code"] == HttpCode.VALIDATE_ERROR.value

    def test_update_document_not_found(self):
        fake_id = uuid.uuid4()
        resp = self.client.put(
            f"/datasets/{self.dataset_id}/documents/{fake_id}",
            json={"name": "任意标题"},
        )
        body = resp.get_json()
        assert body["code"] == HttpCode.NOT_FOUND.value

    def test_update_document_wrong_dataset(self):
        resp = self.client.put(
            f"/datasets/{self.dataset_id}/documents/{self.other_doc_id}",
            json={"name": "任意标题"},
        )
        body = resp.get_json()
        assert body["code"] == HttpCode.NOT_FOUND.value
