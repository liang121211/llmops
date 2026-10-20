import inject
import pytest

from internal.core.message_processor import (
    MAX_SUGGESTED_QUESTION_COUNT,
    ConversationTitle,
    MessageProcessor,
    detect_language,
)
from internal.core.message_processor import message_processor as processor_module
from internal.core.message_processor.prompt_templates import (
    CONVERSATION_TITLE_PROMPT,
    MEMORY_SUMMARY_PROMPT,
)
from internal.pkg.response import HttpCode
from internal.schema.message_schema import MAX_HISTORY_MESSAGE_COUNT


def _fake_chain(capture: dict, output: str):
    """假的 LCEL 链：记录提示词渲染出的变量，返回预先准备好的模型输出。"""

    class Chain:
        def invoke(self, payload):
            capture.update(payload)
            return output

    return Chain()


@pytest.fixture
def processor():
    return MessageProcessor()


class TestPromptTemplates:
    """提示词模板：变量完整，且 JSON 示例的花括号不会被当成模板变量。"""

    def test_memory_summary_prompt_renders_all_variables(self):
        messages = MEMORY_SUMMARY_PROMPT.format(
            original_summary="旧摘要", human_message="用户问题", ai_message="AI回答"
        )
        assert "旧摘要" in messages
        assert "用户问题" in messages
        assert "AI回答" in messages

    def test_conversation_title_prompt_keeps_json_example(self):
        # 模板里的 {"topic": ...} 需要转义，渲染后必须还原成合法 JSON 示例
        messages = CONVERSATION_TITLE_PROMPT.format(
            query="杭州天气", language_hint="中文"
        )
        assert '{"topic": "...", "language": "...", "reason": "..."}' in messages
        assert "杭州天气" in messages


class TestLanguageDetection:
    def test_detect_language(self):
        assert detect_language("杭州今天天气怎么样") == "中文"
        assert detect_language("How is the weather") == "英文"
        assert detect_language("用 python 写一个爬虫") == "中英混合"
        assert detect_language("123456") == "其它"


class TestMemorySummary:
    """长期记忆摘要生成。"""

    def test_generate_summary_strips_model_output(self, processor, monkeypatch):
        capture = {}
        monkeypatch.setattr(
            processor, "_build_chain", lambda prompt: _fake_chain(capture, "  新摘要  ")
        )
        summary = processor.generate_memory_summary("用户问天气", "AI答晴")
        assert summary == "新摘要"
        # 首次生成没有原始摘要时，用占位文案填充，保证提示词字段不为空
        assert capture["original_summary"] == processor_module.EMPTY_SUMMARY_PLACEHOLDER
        assert capture["human_message"] == "用户问天气"
        assert capture["ai_message"] == "AI答晴"

    def test_generate_summary_keeps_original_summary(self, processor, monkeypatch):
        capture = {}
        monkeypatch.setattr(
            processor, "_build_chain", lambda prompt: _fake_chain(capture, "合并摘要")
        )
        processor.generate_memory_summary("新消息", "新回答", "历史摘要")
        assert capture["original_summary"] == "历史摘要"


class TestConversationTitle:
    """会话标题生成，语言需与用户提问一致。"""

    def test_title_from_json_output(self, processor, monkeypatch):
        output = (
            '```json\n{"topic": "杭州天气查询", "language": "中文",'
            ' "reason": "用户询问天气"}\n```'
        )
        monkeypatch.setattr(
            processor, "_build_chain", lambda prompt: _fake_chain({}, output)
        )
        title = processor.generate_conversation_title("杭州今天天气怎么样")
        assert isinstance(title, ConversationTitle)
        assert title.topic == "杭州天气查询"
        assert title.language == "中文"
        assert title.reason == "用户询问天气"

    def test_title_gets_language_hint(self, processor, monkeypatch):
        capture = {}
        output = '{"topic": "Weather in Paris", "language": "英文", "reason": "r"}'
        monkeypatch.setattr(
            processor, "_build_chain", lambda prompt: _fake_chain(capture, output)
        )
        title = processor.generate_conversation_title("How is the weather in Paris")
        # 规则判定的语言会作为提示，帮助模型保持与用户一致
        assert capture["language_hint"] == "英文"
        assert title.topic == "Weather in Paris"
        assert title.language == "英文"

    def test_title_falls_back_when_model_output_is_not_json(
        self, processor, monkeypatch
    ):
        monkeypatch.setattr(
            processor, "_build_chain", lambda prompt: _fake_chain({}, "抱歉，无法生成")
        )
        title = processor.generate_conversation_title("帮我介绍一下北京旅游攻略")
        assert title.topic.startswith("帮我介绍一下北京")
        assert title.language == "中文"
        assert title.reason

    def test_title_fills_language_when_model_omits_it(
        self, processor, monkeypatch
    ):
        monkeypatch.setattr(
            processor,
            "_build_chain",
            lambda prompt: _fake_chain({}, '{"topic": "标题", "language": ""}'),
        )
        title = processor.generate_conversation_title("今天心情不错")
        assert title.language == "中文"


class TestSuggestedQuestions:
    """建议性问题生成，数量不超过 3 个。"""

    def test_questions_parsed_and_capped(self, processor, monkeypatch):
        capture = {}
        output = (
            "1. 杭州明天天气怎么样？\n"
            "2. 需要带伞吗？\n"
            "- 杭州明天天气怎么样？\n"
            "3. 西湖周边有什么推荐？\n"
            "4. 超出上限的问题"
        )
        monkeypatch.setattr(
            processor, "_build_chain", lambda prompt: _fake_chain(capture, output)
        )
        history = [
            {"role": "user", "content": "杭州今天天气如何"},
            {"role": "assistant", "content": "今天晴，25 度"},
        ]
        questions = processor.generate_suggested_questions(history, 3)
        # 编号与前缀被剔除，重复问题被去掉，总数不超过上限
        assert questions == [
            "杭州明天天气怎么样？",
            "需要带伞吗？",
            "西湖周边有什么推荐？",
        ]
        assert capture["limit"] == 3
        assert "用户：杭州今天天气如何" in capture["history"]
        assert "AI：今天晴，25 度" in capture["history"]

    def test_limit_clamped_to_max_count(self, processor, monkeypatch):
        capture = {}
        monkeypatch.setattr(
            processor, "_build_chain", lambda prompt: _fake_chain(capture, "一个问题")
        )
        questions = processor.generate_suggested_questions(
            [{"role": "user", "content": "问题"}], MAX_SUGGESTED_QUESTION_COUNT + 5
        )
        assert capture["limit"] == MAX_SUGGESTED_QUESTION_COUNT
        assert len(questions) == 1

    def test_history_with_blank_content_is_skipped(self, processor, monkeypatch):
        capture = {}
        monkeypatch.setattr(
            processor, "_build_chain", lambda prompt: _fake_chain(capture, "建议")
        )
        processor.generate_suggested_questions(
            [
                {"role": "user", "content": "  "},
                {"role": "assistant", "content": "回答"},
            ],
            3,
        )
        assert capture["history"] == "AI：回答"


@pytest.fixture
def processor_instance():
    """DI 容器里的消息处理器单例，用例用它替换三个能力方法，避免真实调用大模型。"""
    return inject.instance(MessageProcessor)


class TestMemorySummaryAPI:
    """POST /messages/memory-summary"""

    def test_success(self, client, processor_instance, monkeypatch):
        capture = {}

        def fake_summary(human_message, ai_message, original_summary=""):
            capture.update(
                human_message=human_message,
                ai_message=ai_message,
                original_summary=original_summary,
            )
            return "用户咨询杭州天气，AI回答晴转多云"

        monkeypatch.setattr(processor_instance, "generate_memory_summary", fake_summary)
        body = client.post(
            "/messages/memory-summary",
            json={
                "human_message": "杭州今天天气怎么样",
                "ai_message": "今天晴，25 度",
                "original_summary": "用户在规划杭州行程",
            },
        ).get_json()
        assert body["code"] == HttpCode.SUCCESS.value
        assert body["data"]["summary"] == "用户咨询杭州天气，AI回答晴转多云"
        assert capture["original_summary"] == "用户在规划杭州行程"

    def test_success_without_original_summary(self, client, processor_instance, monkeypatch):
        capture = {}
        monkeypatch.setattr(
            processor_instance,
            "generate_memory_summary",
            lambda human_message, ai_message, original_summary="": (
                capture.update(original_summary=original_summary) or "摘要"
            ),
        )
        body = client.post(
            "/messages/memory-summary",
            json={"human_message": "杭州天气", "ai_message": "晴"},
        ).get_json()
        assert body["code"] == HttpCode.SUCCESS.value
        # 未传原始摘要时按空字符串处理，由核心层补占位文案
        assert capture["original_summary"] == ""

    def test_missing_required_fields(self, client):
        body = client.post("/messages/memory-summary", json={}).get_json()
        assert body["code"] == HttpCode.VALIDATE_ERROR.value
        assert "human_message" in body["message"]

    def test_missing_ai_message_only(self, client):
        body = client.post(
            "/messages/memory-summary", json={"human_message": "杭州天气"}
        ).get_json()
        assert body["code"] == HttpCode.VALIDATE_ERROR.value
        assert "ai_message" in body["message"]

    def test_ai_message_too_long(self, client):
        body = client.post(
            "/messages/memory-summary",
            json={"human_message": "杭州天气", "ai_message": "长" * 4001},
        ).get_json()
        assert body["code"] == HttpCode.VALIDATE_ERROR.value
        assert "ai_message" in body["message"]


class TestConversationTitleAPI:
    """POST /messages/conversation-title"""

    def test_success(self, client, processor_instance, monkeypatch):
        monkeypatch.setattr(
            processor_instance,
            "generate_conversation_title",
            lambda query: ConversationTitle(
                topic="杭州天气查询", language="中文", reason="用户询问天气"
            ),
        )
        body = client.post(
            "/messages/conversation-title", json={"query": "杭州今天天气怎么样"}
        ).get_json()
        assert body["code"] == HttpCode.SUCCESS.value
        assert body["data"]["title"] == {
            "topic": "杭州天气查询",
            "language": "中文",
            "reason": "用户询问天气",
        }

    def test_missing_query(self, client):
        body = client.post("/messages/conversation-title", json={}).get_json()
        assert body["code"] == HttpCode.VALIDATE_ERROR.value
        assert "query" in body["message"]


class TestSuggestedQuestionsAPI:
    """POST /messages/suggested-questions"""

    def test_success(self, client, processor_instance, monkeypatch):
        capture = {}

        def fake_generate(history, limit):
            capture["history"] = history
            capture["limit"] = limit
            return ["明天天气如何？", "需要带伞吗？"]

        monkeypatch.setattr(processor_instance, "generate_suggested_questions", fake_generate)
        body = client.post(
            "/messages/suggested-questions",
            json={
                "history": [
                    {"role": "user", "content": "杭州今天天气如何"},
                    {"role": "assistant", "content": "今天晴，25 度"},
                ]
            },
        ).get_json()
        assert body["code"] == HttpCode.SUCCESS.value
        assert body["data"]["questions"] == ["明天天气如何？", "需要带伞吗？"]
        # 默认数量为上限值，历史对话原样透传
        assert capture["limit"] == MAX_SUGGESTED_QUESTION_COUNT
        assert len(capture["history"]) == 2

    def test_custom_limit(self, client, processor_instance, monkeypatch):
        capture = {}
        monkeypatch.setattr(
            processor_instance,
            "generate_suggested_questions",
            lambda history, limit: capture.update(limit=limit) or ["问题"],
        )
        body = client.post(
            "/messages/suggested-questions",
            json={
                "history": [{"role": "user", "content": "杭州天气"}],
                "limit": 2,
            },
        ).get_json()
        assert body["code"] == HttpCode.SUCCESS.value
        assert capture["limit"] == 2

    def test_missing_history(self, client):
        body = client.post("/messages/suggested-questions", json={}).get_json()
        assert body["code"] == HttpCode.VALIDATE_ERROR.value
        assert "history" in body["message"]

    @pytest.mark.parametrize("payload", [
        {"history": []},
        {"history": "杭州天气"},
        {"history": [{"role": "user", "content": "  "}]},
        {"history": [{"content": "没有角色"}]},
        {"history": ["字符串元素"]},
    ])
    def test_invalid_history(self, client, payload):
        body = client.post("/messages/suggested-questions", json=payload).get_json()
        assert body["code"] == HttpCode.VALIDATE_ERROR.value
        assert "history" in body["message"]

    @pytest.mark.parametrize("limit", [0, 4, "abc"])
    def test_invalid_limit(self, client, limit):
        body = client.post(
            "/messages/suggested-questions",
            json={"history": [{"role": "user", "content": "杭州天气"}], "limit": limit},
        ).get_json()
        assert body["code"] == HttpCode.FAIL.value
        assert "limit" in body["message"]

    def test_history_too_long(self, client):
        history = [
            {"role": "user", "content": f"第{i}条消息"}
            for i in range(MAX_HISTORY_MESSAGE_COUNT + 1)
        ]
        body = client.post(
            "/messages/suggested-questions", json={"history": history}
        ).get_json()
        assert body["code"] == HttpCode.VALIDATE_ERROR.value
        assert "history" in body["message"]
