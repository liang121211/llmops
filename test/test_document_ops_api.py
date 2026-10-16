import uuid

import pytest

from internal.entity import DocumentStatus
from internal.model.document import Document
from internal.pkg.response.http_code import HttpCode
from internal.service.document_service import DocumentService

# inject 的 autoparams 会把类替换成包装函数，真实类在 __wrapped__ 上，
# monkeypatch 必须打在真实类才能生效
_REAL_DOCUMENT_SERVICE = DocumentService.__wrapped__


class TestDocumentOpsAPI:
    """文档禁用/启用/删除接口测试，异步任务提交被拦截为本地记录。"""

    @pytest.fixture(autouse=True)
    def setup(self, client, app_context, monkeypatch):
        self.client = client
        self.submitted = {"disable": [], "enable": [], "delete": []}

        def _fake(name):
            def _trigger(self_service, document_ids):
                self.submitted[name] = list(document_ids)

            return _trigger

        monkeypatch.setattr(_REAL_DOCUMENT_SERVICE, "trigger_disable", _fake("disable"))
        monkeypatch.setattr(_REAL_DOCUMENT_SERVICE, "trigger_enable", _fake("enable"))
        monkeypatch.setattr(_REAL_DOCUMENT_SERVICE, "trigger_delete", _fake("delete"))

        from pkg.sqlalchemy import db
        from internal.model.dataset import Dataset
        from internal.model.process_rule import ProcessRule

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
                        name=f"ops_api_ds_{ds_id.hex[:8]}",
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
            self.doc = Document(
                account_id=self.account_id,
                dataset_id=self.dataset_id,
                upload_file_id=uuid.uuid4(),
                process_rule_id=pr.id,
                batch="2026101500000033334444",
                name="ops_api.txt",
                position=1,
                status=DocumentStatus.COMPLETED,
                enabled=True,
            )
            db.session.add(self.doc)
            db.session.flush()
            self.other_doc = Document(
                account_id=self.account_id,
                dataset_id=self.other_dataset_id,
                upload_file_id=uuid.uuid4(),
                process_rule_id=pr.id,
                batch="2026101500000055556666",
                name="ops_other.txt",
                position=1,
                status=DocumentStatus.COMPLETED,
                enabled=True,
            )
            db.session.add(self.other_doc)
            db.session.flush()
            self.process_rule_id = pr.id

        yield

        from sqlalchemy import delete as sa_delete

        with db.auto_commit():
            db.session.execute(
                sa_delete(Document).where(
                    Document.id.in_([self.doc.id, self.other_doc.id])
                )
            )
            db.session.execute(
                sa_delete(ProcessRule).where(ProcessRule.id == self.process_rule_id)
            )
            db.session.execute(
                sa_delete(Dataset).where(
                    Dataset.id.in_([self.dataset_id, self.other_dataset_id])
                )
            )

    def _set_status(self, status):
        with self.db.auto_commit():
            doc = self.db.session.get(Document, self.doc.id)
            doc.status = status

    # ── 禁用 ──────────────────────────────────────────────────────

    def test_disable_submits_task(self):
        resp = self.client.put(
            f"/datasets/{self.dataset_id}/documents/{self.doc.id}/disable"
        )
        body = resp.get_json()
        assert body["code"] == HttpCode.SUCCESS.value
        assert self.submitted["disable"] == [str(self.doc.id)]

    def test_disable_rejected_while_processing(self):
        self._set_status(DocumentStatus.INDEXING)
        resp = self.client.put(
            f"/datasets/{self.dataset_id}/documents/{self.doc.id}/disable"
        )
        body = resp.get_json()
        assert body["code"] == HttpCode.FAIL.value
        assert self.submitted["disable"] == []

    def test_disable_nonexistent_document(self):
        fake_id = uuid.uuid4()
        resp = self.client.put(
            f"/datasets/{self.dataset_id}/documents/{fake_id}/disable"
        )
        body = resp.get_json()
        assert body["code"] == HttpCode.NOT_FOUND.value

    def test_disable_wrong_dataset(self):
        resp = self.client.put(
            f"/datasets/{self.dataset_id}/documents/{self.other_doc.id}/disable"
        )
        body = resp.get_json()
        assert body["code"] == HttpCode.NOT_FOUND.value

    # ── 启用 ──────────────────────────────────────────────────────

    def test_enable_submits_task(self):
        resp = self.client.put(
            f"/datasets/{self.dataset_id}/documents/{self.doc.id}/enable"
        )
        body = resp.get_json()
        assert body["code"] == HttpCode.SUCCESS.value
        assert self.submitted["enable"] == [str(self.doc.id)]

    def test_enable_rejected_while_processing(self):
        self._set_status(DocumentStatus.PARSING)
        resp = self.client.put(
            f"/datasets/{self.dataset_id}/documents/{self.doc.id}/enable"
        )
        body = resp.get_json()
        assert body["code"] == HttpCode.FAIL.value

    # ── 删除 ──────────────────────────────────────────────────────

    def test_delete_submits_task(self):
        resp = self.client.delete(
            f"/datasets/{self.dataset_id}/documents/{self.doc.id}"
        )
        body = resp.get_json()
        assert body["code"] == HttpCode.SUCCESS.value
        assert self.submitted["delete"] == [str(self.doc.id)]

    def test_delete_rejected_while_processing(self):
        self._set_status(DocumentStatus.SPLITTING)
        resp = self.client.delete(
            f"/datasets/{self.dataset_id}/documents/{self.doc.id}"
        )
        body = resp.get_json()
        assert body["code"] == HttpCode.FAIL.value
        assert self.submitted["delete"] == []

    def test_delete_allows_error_document(self):
        self._set_status(DocumentStatus.ERROR)
        resp = self.client.delete(
            f"/datasets/{self.dataset_id}/documents/{self.doc.id}"
        )
        body = resp.get_json()
        assert body["code"] == HttpCode.SUCCESS.value

    def test_delete_nonexistent_document(self):
        fake_id = uuid.uuid4()
        resp = self.client.delete(
            f"/datasets/{self.dataset_id}/documents/{fake_id}"
        )
        body = resp.get_json()
        assert body["code"] == HttpCode.NOT_FOUND.value
