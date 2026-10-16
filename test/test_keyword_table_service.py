import uuid

import pytest

from internal.model.keyword_table import KeywordTable


class TestKeywordTableService:
    """关键词表服务测试。"""

    @pytest.fixture(autouse=True)
    def setup(self, app_context):
        from pkg.sqlalchemy import db

        self.db = db
        self.dataset_id = uuid.uuid4()
        yield
        with db.auto_commit():
            from sqlalchemy import delete

            db.session.execute(
                delete(KeywordTable).where(
                    KeywordTable.dataset_id == self.dataset_id
                )
            )

    def test_get_or_create_creates_new(self, app_context):
        import inject

        from internal.service.keyword_table_service import KeywordTableService

        service = inject.instance(KeywordTableService)
        kt = service.get_or_create_by_dataset_id(self.dataset_id)
        assert kt is not None
        assert kt.dataset_id == self.dataset_id
        assert kt.keyword_table == {}

    def test_get_or_create_returns_existing(self, app_context):
        import inject

        from internal.service.keyword_table_service import KeywordTableService

        service = inject.instance(KeywordTableService)
        kt1 = service.get_or_create_by_dataset_id(self.dataset_id)
        kt2 = service.get_or_create_by_dataset_id(self.dataset_id)
        assert kt1.id == kt2.id

    def test_update_keyword_table(self, app_context):
        import inject

        from internal.service.keyword_table_service import KeywordTableService

        service = inject.instance(KeywordTableService)
        data = {"关键词1": ["seg_1", "seg_2"], "关键词2": ["seg_3"]}
        kt = service.update_keyword_table(self.dataset_id, data)
        assert kt.keyword_table == data

    def test_add_segments_keywords(self, app_context):
        import inject

        from internal.service.keyword_table_service import KeywordTableService

        service = inject.instance(KeywordTableService)
        service.add_segments_keywords(
            self.dataset_id,
            {"seg_1": ["苹果", "水果"], "seg_2": ["苹果", "价格"]},
        )
        kt = service.get_or_create_by_dataset_id(self.dataset_id)
        assert kt.keyword_table == {
            "苹果": ["seg_1", "seg_2"],
            "水果": ["seg_1"],
            "价格": ["seg_2"],
        }

    def test_add_segments_keywords_no_duplicate(self, app_context):
        import inject

        from internal.service.keyword_table_service import KeywordTableService

        service = inject.instance(KeywordTableService)
        service.add_segments_keywords(self.dataset_id, {"seg_1": ["苹果"]})
        service.add_segments_keywords(self.dataset_id, {"seg_1": ["苹果", "香蕉"]})
        kt = service.get_or_create_by_dataset_id(self.dataset_id)
        assert kt.keyword_table["苹果"] == ["seg_1"]
        assert kt.keyword_table["香蕉"] == ["seg_1"]

    def test_remove_segments_keywords(self, app_context):
        import inject

        from internal.service.keyword_table_service import KeywordTableService

        service = inject.instance(KeywordTableService)
        service.add_segments_keywords(
            self.dataset_id,
            {"seg_1": ["苹果", "水果"], "seg_2": ["苹果"]},
        )
        service.remove_segments_keywords(self.dataset_id, ["seg_1"])
        kt = service.get_or_create_by_dataset_id(self.dataset_id)
        # 水果只被 seg_1 引用，应整体删除；苹果还剩 seg_2
        assert kt.keyword_table == {"苹果": ["seg_2"]}

    def test_remove_all_leaves_empty_table(self, app_context):
        import inject

        from internal.service.keyword_table_service import KeywordTableService

        service = inject.instance(KeywordTableService)
        service.add_segments_keywords(self.dataset_id, {"seg_1": ["苹果"]})
        service.remove_segments_keywords(self.dataset_id, ["seg_1"])
        kt = service.get_or_create_by_dataset_id(self.dataset_id)
        assert kt.keyword_table == {}
