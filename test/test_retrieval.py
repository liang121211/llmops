import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import inject
import pytest
from sqlalchemy import delete as sa_delete

from internal.core.keyword_extractor import extract_keywords
from internal.entity import DocumentStatus, QuerySource, SegmentStatus
from internal.model.dataset import Dataset
from internal.model.dataset_query import DatasetQuery
from internal.model.document import Document
from internal.model.keyword_table import KeywordTable
from internal.model.process_rule import ProcessRule
from internal.model.segment import Segment
from internal.model.upload_file import UploadFile
from internal.pkg.response import HttpCode
from internal.service.keyword_table_service import KeywordTableService

ACCOUNT_ID = uuid.UUID("a666a888-8888-6666-1234-b9d69212aaaa")


class TestHitTestingAPI:
    """召回测试接口：路由、校验、全文召回结果结构与查询记录写入。

    向量检索依赖真实 Weaviate，这里用 mock 替换 vector_store_service，
    全文检索则用真实词表与 DB 片段，保证用例不依赖外部服务。
    """

    @pytest.fixture(autouse=True)
    def setup(self, client, app_context):
        from app.http.app import app
        from pkg.sqlalchemy import db

        self.client = client
        self.db = db
        self.dataset_id = uuid.uuid4()
        self.query_text = "手工牛肉丸的制作方法与福建特色"
        self.vector_mock = MagicMock()
        self.vector_mock.search_by_vector.return_value = []

        # 路由在导入期创建 handler 实例，直接替换其检索服务的向量依赖
        handler = app.view_functions["app.hit_testing"].__self__
        handler.retrieval_service.vector_store_service = self.vector_mock

        with db.auto_commit():
            db.session.add(
                Dataset(
                    id=self.dataset_id,
                    account_id=ACCOUNT_ID,
                    name=f"rt_ds_{self.dataset_id.hex[:8]}",
                    description="test",
                )
            )
            uf = UploadFile(
                account_id=ACCOUNT_ID,
                name="beef_ball.txt",
                key="t/beef_ball.txt",
                size=10,
                extension="txt",
                mime_type="text/plain",
                hash="h",
            )
            db.session.add(uf)
            pr = ProcessRule(
                account_id=ACCOUNT_ID,
                dataset_id=self.dataset_id,
                mode="automatic",
                rule={},
            )
            db.session.add(pr)
            db.session.flush()
            self.upload_file_id = uf.id
            self.process_rule_id = pr.id
            self.doc = Document(
                account_id=ACCOUNT_ID,
                dataset_id=self.dataset_id,
                upload_file_id=uf.id,
                process_rule_id=pr.id,
                batch="2026101600000099990000",
                name="beef_ball.txt",
                position=1,
                status=DocumentStatus.COMPLETED,
                enabled=True,
            )
            db.session.add(self.doc)
            db.session.flush()
            self.doc_id = self.doc.id
            self.segment = Segment(
                account_id=ACCOUNT_ID,
                dataset_id=self.dataset_id,
                document_id=self.doc.id,
                node_id=str(uuid.uuid4()),
                position=0,
                content=self.query_text,
                character_count=len(self.query_text),
                keywords=[],
                status=SegmentStatus.COMPLETED,
                enabled=True,
            )
            db.session.add(self.segment)
            db.session.flush()
            self.segment_id = self.segment.id

        # 用真实词表服务写入倒排表：关键词 -> 片段 id，保证全文检索能命中
        keywords = extract_keywords(self.query_text)
        assert keywords, "查询应至少提取到一个关键词，否则用例前提不成立"
        inject.instance(KeywordTableService).add_segments_keywords(
            self.dataset_id, {str(self.segment_id): keywords}
        )

        yield

        with db.auto_commit():
            self.db.session.execute(
                sa_delete(Segment).where(Segment.document_id == self.doc_id)
            )
            self.db.session.execute(
                sa_delete(DatasetQuery).where(DatasetQuery.dataset_id == self.dataset_id)
            )
            self.db.session.execute(
                sa_delete(KeywordTable).where(KeywordTable.dataset_id == self.dataset_id)
            )
            self.db.session.execute(
                sa_delete(Document).where(Document.id == self.doc_id)
            )
            self.db.session.execute(
                sa_delete(ProcessRule).where(ProcessRule.id == self.process_rule_id)
            )
            self.db.session.execute(
                sa_delete(UploadFile).where(UploadFile.id == self.upload_file_id)
            )
            self.db.session.execute(
                sa_delete(Dataset).where(Dataset.id == self.dataset_id)
            )

    def test_full_text_returns_records_with_score_and_document_info(self):
        body = self.client.post(
            f"/datasets/{self.dataset_id}/hit-testing",
            json={"query": self.query_text, "retrieval_strategy": "full_text"},
        ).get_json()

        assert body["code"] == HttpCode.SUCCESS.value
        records = body["data"]["records"]
        assert len(records) == 1
        record = records[0]
        assert record["segment"]["id"] == str(self.segment_id)
        assert record["segment"]["content"] == self.query_text
        assert record["score"] > 0
        # 文档信息应包含上传文件的扩展名与媒体类型
        assert record["document"]["name"] == "beef_ball.txt"
        assert record["document"]["extension"] == "txt"
        assert record["document"]["mime_type"] == "text/plain"

    def test_hit_testing_writes_recall_test_query_record(self):
        self.client.post(
            f"/datasets/{self.dataset_id}/hit-testing",
            json={"query": self.query_text, "retrieval_strategy": "full_text"},
        )
        body = self.client.get(f"/datasets/{self.dataset_id}/queries").get_json()
        assert body["code"] == HttpCode.SUCCESS.value
        queries = body["data"]["queries"]
        assert len(queries) >= 1
        assert queries[0]["source"] == QuerySource.RECALL_TEST
        assert queries[0]["query"] == self.query_text

    def test_nonexistent_dataset_returns_not_found(self):
        body = self.client.post(
            f"/datasets/{uuid.uuid4()}/hit-testing",
            json={"query": self.query_text},
        ).get_json()
        assert body["code"] == HttpCode.NOT_FOUND.value

    def test_missing_query_fails_validation(self):
        body = self.client.post(
            f"/datasets/{self.dataset_id}/hit-testing", json={}
        ).get_json()
        assert body["code"] == HttpCode.VALIDATE_ERROR.value

    def test_invalid_strategy_fails_validation(self):
        body = self.client.post(
            f"/datasets/{self.dataset_id}/hit-testing",
            json={"query": self.query_text, "retrieval_strategy": "not_a_strategy"},
        ).get_json()
        assert body["code"] == HttpCode.VALIDATE_ERROR.value

    def test_k_out_of_range_fails(self):
        body = self.client.post(
            f"/datasets/{self.dataset_id}/hit-testing",
            json={"query": self.query_text, "k": 999},
        ).get_json()
        assert body["code"] == HttpCode.FAIL.value
        assert "k" in body["message"]


class TestDatasetQueriesAPI:
    """检索记录查询接口：404、默认条数、limit 参数与倒序排列。"""

    @pytest.fixture(autouse=True)
    def setup(self, client, app_context):
        from pkg.sqlalchemy import db

        self.client = client
        self.db = db
        self.dataset_id = uuid.uuid4()
        with db.auto_commit():
            db.session.add(
                Dataset(
                    id=self.dataset_id,
                    account_id=ACCOUNT_ID,
                    name=f"q_ds_{self.dataset_id.hex[:8]}",
                    description="test",
                )
            )
            base = datetime.now() - timedelta(hours=1)
            for i in range(12):
                db.session.add(
                    DatasetQuery(
                        dataset_id=self.dataset_id,
                        query=f"记录{i}",
                        source=QuerySource.RECALL_TEST,
                        created_by=ACCOUNT_ID,
                        created_at=base + timedelta(seconds=i),
                    )
                )
        yield
        with db.auto_commit():
            self.db.session.execute(
                sa_delete(DatasetQuery).where(DatasetQuery.dataset_id == self.dataset_id)
            )
            self.db.session.execute(
                sa_delete(Dataset).where(Dataset.id == self.dataset_id)
            )

    def test_nonexistent_dataset_returns_not_found(self):
        body = self.client.get(f"/datasets/{uuid.uuid4()}/queries").get_json()
        assert body["code"] == HttpCode.NOT_FOUND.value

    def test_default_returns_ten_records_desc_order(self):
        body = self.client.get(f"/datasets/{self.dataset_id}/queries").get_json()
        assert body["code"] == HttpCode.SUCCESS.value
        queries = body["data"]["queries"]
        assert len(queries) == 10
        # 按创建时间倒序，最新的“记录11”排在最前
        assert queries[0]["query"] == "记录11"

    def test_limit_param_respected(self):
        body = self.client.get(
            f"/datasets/{self.dataset_id}/queries?limit=3"
        ).get_json()
        assert body["code"] == HttpCode.SUCCESS.value
        assert len(body["data"]["queries"]) == 3

    def test_invalid_limit_fails(self):
        body = self.client.get(
            f"/datasets/{self.dataset_id}/queries?limit=abc"
        ).get_json()
        assert body["code"] == HttpCode.FAIL.value
