import re
from dataclasses import dataclass
from typing import Callable, ClassVar

import inject
from langchain_text_splitters import RecursiveCharacterTextSplitter

from internal.model.process_rule import ProcessRule
from internal.service.base_service import BaseService
from pkg.sqlalchemy import SQLAlchemy


@inject.autoparams()
@dataclass
class ProcessRuleService(BaseService[ProcessRule]):
    """处理规则服务，提供文本分割器构建和预处理能力。"""

    db: SQLAlchemy
    model: ClassVar[type[ProcessRule]] = ProcessRule

    def get_text_splitter(
        self,
        rule: dict,
        length_function: Callable[[str], int] = len,
        **kwargs,
    ) -> RecursiveCharacterTextSplitter:
        """根据处理规则构建递归文本分割器。"""
        segment = rule.get("segment", {})
        return RecursiveCharacterTextSplitter(
            separators=segment.get("separators", ["\n\n", "\n"]),
            chunk_size=segment.get("chunk_size", 500),
            chunk_overlap=segment.get("chunk_overlap", 50),
            length_function=length_function,
            **kwargs,
        )

    @staticmethod
    def pre_process_text(text: str, rule: dict) -> str:
        """根据预处理规则清洗文本，去除多余空格、链接、邮箱等。"""
        pre_rules = rule.get("pre_process_rules", [])
        # 先执行内容删除类规则，最后再清理多余空格
        ordered = sorted(pre_rules, key=lambda r: 1 if r.get("id") == "remove_extra_space" else 0)
        for pr in ordered:
            rule_id = pr.get("id", "")
            enabled = pr.get("enabled", False)
            if not enabled:
                continue
            if rule_id == "remove_extra_space":
                text = re.sub(r"\s+", " ", text).strip()
            elif rule_id == "remove_url_and_email":
                text = re.sub(r"https?://\S+|www\.\S+", "", text)
                text = re.sub(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "", text)
        return text


__all__ = ["ProcessRuleService"]
