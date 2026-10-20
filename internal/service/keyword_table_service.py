from dataclasses import dataclass
from typing import Any, ClassVar

import inject
from sqlalchemy import select

from internal.lib.redis_lock import keyword_table_lock_key, redis_lock
from internal.model.keyword_table import KeywordTable
from internal.service.base_service import BaseService
from pkg.sqlalchemy import SQLAlchemy


@inject.autoparams()
@dataclass
class KeywordTableService(BaseService[KeywordTable]):
    """关键词表服务，管理知识库级别的关键词索引数据。"""

    db: SQLAlchemy
    model: ClassVar[type[KeywordTable]] = KeywordTable

    def get_or_create_by_dataset_id(self, dataset_id: Any) -> KeywordTable:
        """获取知识库对应的关键词表，不存在则新建一条空记录。"""
        kt = self.get_first(KeywordTable.dataset_id == dataset_id)
        if kt is not None:
            return kt
        return self.create(dataset_id=dataset_id, keyword_table={})

    def get_by_document_id(self, document_id: Any) -> KeywordTable | None:
        """根据文档 ID 获取所属知识库的关键词表。"""
        from internal.model.document import Document

        doc = self.db.session.get(Document, document_id)
        if doc is None:
            return None
        return self.get_first(KeywordTable.dataset_id == doc.dataset_id)

    def get_by_segment_id(self, segment_id: Any) -> KeywordTable | None:
        """根据片段 ID 获取所属知识库的关键词表。"""
        from internal.model.segment import Segment

        seg = self.db.session.get(Segment, segment_id)
        if seg is None:
            return None
        return self.get_first(KeywordTable.dataset_id == seg.dataset_id)

    def update_keyword_table(self, dataset_id: Any, keyword_table: dict) -> KeywordTable:
        """更新知识库的关键词表数据。

        低层整体写入：调用方自己负责读-改-写的并发安全，
        业务代码应优先使用下面带分布式锁的 add/remove 方法。
        """
        kt = self.get_or_create_by_dataset_id(dataset_id)
        with self.db.auto_commit():
            kt.keyword_table = keyword_table
        return kt

    def search_segments_by_keywords(
        self, dataset_id: Any, keywords: list[str]
    ) -> dict[str, list[str]]:
        """按查询关键词在倒排表里检索，返回命中片段到命中关键词列表的映射。

        只读不建表：知识库还没有关键词表时直接返回空。
        命中数越多说明片段与查询的相关度越高，由上层换算成打分。
        """
        kt = self.get_first(KeywordTable.dataset_id == dataset_id)
        if kt is None or not kt.keyword_table:
            return {}
        table = kt.keyword_table
        matches: dict[str, list[str]] = {}
        for keyword in keywords:
            for segment_id in table.get(keyword, []):
                matches.setdefault(segment_id, []).append(keyword)
        return matches

    def add_segments_keywords(
        self, dataset_id: Any, keywords_map: dict[str, list[str]]
    ) -> None:
        """把多个片段的关键词并入关键词表（segment_id -> 关键词列表）。

        整个读取-合并-写回过程持有关键词表缓存锁，
        防止并发构建/启用时后写覆盖前写造成数据不一致。
        """
        with redis_lock(keyword_table_lock_key(dataset_id)):
            kt = self.get_or_create_by_dataset_id(dataset_id)
            table = dict(kt.keyword_table or {})
            for segment_id, keywords in keywords_map.items():
                for keyword in keywords:
                    ids = table.setdefault(keyword, [])
                    if segment_id not in ids:
                        ids.append(segment_id)
            with self.db.auto_commit():
                kt.keyword_table = table

    def remove_segments_keywords(self, dataset_id: Any, segment_ids: list[str]) -> None:
        """把指定片段从关键词表中全部移除，没有任何片段引用的关键词一并删除。"""
        removed = set(segment_ids)
        with redis_lock(keyword_table_lock_key(dataset_id)):
            kt = self.get_or_create_by_dataset_id(dataset_id)
            table = dict(kt.keyword_table or {})
            new_table: dict[str, list[str]] = {}
            for keyword, ids in table.items():
                rest = [i for i in ids if i not in removed]
                if rest:
                    new_table[keyword] = rest
            with self.db.auto_commit():
                kt.keyword_table = new_table


__all__ = ["KeywordTableService"]
