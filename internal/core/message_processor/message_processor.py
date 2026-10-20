import json
import re
from dataclasses import dataclass

import inject
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

from internal.core.message_processor.conversation_title_schema import (
    ConversationTitle,
)
from internal.core.message_processor.prompt_templates import (
    CONVERSATION_TITLE_PROMPT,
    MEMORY_SUMMARY_PROMPT,
    SUGGESTED_QUESTION_PROMPT,
)

# 消息处理统一使用的对话模型，与智能体应用保持一致
DEFAULT_MODEL_NAME = "deepseek-v4-flash"
# 建议性问题的数量上限
MAX_SUGGESTED_QUESTION_COUNT = 3
# 摘要为空时的占位文案，让提示词始终有"原始摘要"字段
EMPTY_SUMMARY_PLACEHOLDER = "（暂无）"
# 会话标题最大长度，超出则截断
MAX_TITLE_LENGTH = 30

_CJK_PATTERN = re.compile(r"[\u4e00-\u9fff]")
_LATIN_PATTERN = re.compile(r"[A-Za-z]")
# 行首的编号与项目符号，解析建议性问题时需要剔除
_LINE_PREFIX_PATTERN = re.compile(r"^\s*(?:[-*•]|\d+[.、)])\s*")


def detect_language(text: str) -> str:
    """判定文本的语言类型，用于保证标题与用户语言一致。"""
    has_cjk = bool(_CJK_PATTERN.search(text))
    has_latin = bool(_LATIN_PATTERN.search(text))
    if has_cjk and has_latin:
        return "中英混合"
    if has_cjk:
        return "中文"
    if has_latin:
        return "英文"
    return "其它"


def _extract_json_object(text: str) -> dict:
    """从模型输出里取出第一个 JSON 对象，兼容 ```json 代码块包裹的情况。"""
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("模型输出中不存在 JSON 对象")
    return json.loads(cleaned[start : end + 1])


@inject.autoparams()
@dataclass
class MessageProcessor:
    """AI 消息处理核心：长期记忆摘要、会话标题、建议性问题。"""

    def _build_chain(self, prompt):
        # 摘要、标题、建议问题都要求稳定输出，因此温度取 0
        model = ChatOpenAI(model=DEFAULT_MODEL_NAME, temperature=0)
        return prompt | model | StrOutputParser()

    def generate_memory_summary(
        self,
        human_message: str,
        ai_message: str,
        original_summary: str = "",
    ) -> str:
        """把最新一轮对话压缩进原始摘要，生成长期记忆。"""
        summary = self._build_chain(MEMORY_SUMMARY_PROMPT).invoke(
            {
                "original_summary": original_summary or EMPTY_SUMMARY_PLACEHOLDER,
                "human_message": human_message,
                "ai_message": ai_message,
            }
        )
        return summary.strip()

    def generate_conversation_title(self, query: str) -> ConversationTitle:
        """根据用户首句提问生成会话主题，语言与提问保持一致。"""
        language_hint = detect_language(query)
        raw = self._build_chain(CONVERSATION_TITLE_PROMPT).invoke(
            {"query": query, "language_hint": language_hint}
        )
        try:
            # 模型输出的是 JSON，解析成 BaseModel 返回给上层
            data = _extract_json_object(raw)
            title = ConversationTitle(
                topic=str(data.get("topic", "")).strip(),
                language=str(data.get("language", "")).strip(),
                reason=str(data.get("reason", "")).strip(),
            )
        except (ValueError, json.JSONDecodeError):
            # 解析失败时兜底：直接截取用户提问作为标题，语言用规则判定
            title = ConversationTitle(topic="", language="", reason="")
        if not title.topic:
            title = title.model_copy(
                update={
                    "topic": query.strip()[:MAX_TITLE_LENGTH],
                    "language": language_hint,
                    "reason": "模型未按格式返回，直接截取用户提问作为会话主题",
                }
            )
        elif not title.language:
            title = title.model_copy(update={"language": language_hint})
        return title

    def generate_suggested_questions(
        self, history: list[dict], limit: int = MAX_SUGGESTED_QUESTION_COUNT
    ) -> list[str]:
        """根据历史对话推测用户接下来最可能提问的问题，数量不超过 limit。"""
        limit = max(1, min(limit, MAX_SUGGESTED_QUESTION_COUNT))
        raw = self._build_chain(SUGGESTED_QUESTION_PROMPT).invoke(
            {"history": self._format_history(history), "limit": limit}
        )
        questions = []
        for line in raw.splitlines():
            question = _LINE_PREFIX_PATTERN.sub("", line).strip()
            # 去掉模型可能带上的引号，并做去重，保证建议干净可用
            question = question.strip("\"'“”")
            if question and question not in questions:
                questions.append(question)
        return questions[:limit]

    @staticmethod
    def _format_history(history: list[dict]) -> str:
        """把 role/content 结构的对话历史渲染成提示词可读的文本。"""
        role_label = {"user": "用户", "human": "用户", "assistant": "AI", "ai": "AI"}
        lines = []
        for item in history:
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            label = role_label.get(str(item.get("role", "")).lower(), "其它")
            lines.append(f"{label}：{content}")
        return "\n".join(lines)


__all__ = ["MessageProcessor", "ConversationTitle", "detect_language"]
