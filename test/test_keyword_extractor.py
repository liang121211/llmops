import pytest

from internal.core.keyword_extractor import STOPWORD_SET, extract_keywords
from internal.pkg.response.http_code import HttpCode


class TestExtractKeywords:
    """关键词提取核心函数测试。"""

    def test_basic_extraction(self):
        text = "自然语言处理是人工智能领域的重要研究方向，涉及文本分析、语义理解和机器翻译等技术"
        keywords = extract_keywords(text)
        assert isinstance(keywords, list)
        assert len(keywords) > 0
        assert len(keywords) <= 10

    def test_max_keyword_limit(self):
        text = "深度学习神经网络卷积循环注意力机制Transformer编码器解码器预训练微调迁移学习生成对抗"
        keywords = extract_keywords(text, max_keyword_per_chunk=3)
        assert len(keywords) <= 3

    def test_empty_text_returns_empty_list(self):
        assert extract_keywords("") == []
        assert extract_keywords("   ") == []

    def test_none_text_returns_empty_list(self):
        assert extract_keywords(None) == []

    def test_stopwords_filtered(self):
        text = "这是一个非常好的测试用例，我们可以用它来验证功能是否正常"
        keywords = extract_keywords(text)
        for word in keywords:
            assert word not in STOPWORD_SET

    def test_short_text(self):
        keywords = extract_keywords("机器学习")
        assert isinstance(keywords, list)

    def test_english_text(self):
        text = "Machine learning is a subset of artificial intelligence that focuses on building systems"
        keywords = extract_keywords(text)
        assert isinstance(keywords, list)
        for word in keywords:
            assert word.lower() not in {"a", "an", "the", "is", "of", "on"}

    def test_default_max_keyword_per_chunk(self):
        text = "知识图谱构建实体关系抽取链接推理问答系统对话管理多轮交互意图识别槽位填充"
        keywords = extract_keywords(text)
        assert len(keywords) <= 10


class TestKeywordExtractAPI:
    """关键词提取接口测试。"""

    @pytest.fixture(autouse=True)
    def setup(self, client):
        self.client = client
        self.url = "/keywords/extract"

    def test_extract_success(self):
        resp = self.client.post(self.url, json={
            "text": "自然语言处理是人工智能的核心技术之一",
        })
        body = resp.get_json()
        assert body["code"] == HttpCode.SUCCESS.value
        assert "keywords" in body["data"]
        assert isinstance(body["data"]["keywords"], list)

    def test_extract_with_custom_max(self):
        resp = self.client.post(self.url, json={
            "text": "深度学习在计算机视觉和自然语言处理领域取得了突破性进展",
            "max_keyword_per_chunk": 3,
        })
        body = resp.get_json()
        assert body["code"] == HttpCode.SUCCESS.value
        assert len(body["data"]["keywords"]) <= 3

    def test_extract_missing_text(self):
        resp = self.client.post(self.url, json={})
        body = resp.get_json()
        assert body["code"] != HttpCode.SUCCESS.value

    def test_extract_empty_text(self):
        resp = self.client.post(self.url, json={"text": ""})
        body = resp.get_json()
        assert body["code"] != HttpCode.SUCCESS.value

    def test_extract_invalid_max_keyword(self):
        resp = self.client.post(self.url, json={
            "text": "测试文本",
            "max_keyword_per_chunk": -1,
        })
        body = resp.get_json()
        assert body["code"] != HttpCode.SUCCESS.value
