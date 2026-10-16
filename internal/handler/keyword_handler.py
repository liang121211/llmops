from flask import request

from internal.core.keyword_extractor import extract_keywords
from internal.pkg.response import fail_message, success_json


class KeywordHandler:
    """关键词提取控制层。"""

    @staticmethod
    def extract():
        payload = request.get_json(silent=True) or {}
        text = payload.get("text")
        if not text or not isinstance(text, str) or not text.strip():
            return fail_message("text 不能为空")
        max_keyword_per_chunk = payload.get("max_keyword_per_chunk", 10)
        if not isinstance(max_keyword_per_chunk, int) or max_keyword_per_chunk <= 0:
            return fail_message("max_keyword_per_chunk 必须为正整数")
        keywords = extract_keywords(text, max_keyword_per_chunk)
        return success_json({"keywords": keywords})


__all__ = ["KeywordHandler"]
