from flask_wtf import FlaskForm
from marshmallow import Schema, fields
from wtforms import StringField
from wtforms.validators import DataRequired, Length, Optional, ValidationError

from internal.core.message_processor import MAX_SUGGESTED_QUESTION_COUNT
from internal.schema.schema import ListField

# 一次建议性问题生成最多允许携带的历史消息条数
MAX_HISTORY_MESSAGE_COUNT = 50


def _validate_history_items(form, field) -> None:
    """校验对话历史：必须是非空数组，且每个元素都带非空的 role 和 content。"""
    data = field.data
    if not isinstance(data, list) or not data:
        raise ValidationError("history参数必须传递且为数组")
    if len(data) > MAX_HISTORY_MESSAGE_COUNT:
        raise ValidationError(f"history最多包含{MAX_HISTORY_MESSAGE_COUNT}条消息")
    for item in data:
        if not isinstance(item, dict):
            raise ValidationError("history中的元素必须是对象")
        role = item.get("role")
        content = item.get("content")
        if not isinstance(role, str) or not role.strip():
            raise ValidationError("history中的元素必须包含非空的role")
        if not isinstance(content, str) or not content.strip():
            raise ValidationError("history中的元素必须包含非空的content")


def parse_suggested_limit(limit) -> tuple[int, str | None]:
    """解析建议性问题数量，取值范围 1-3，返回 (数量, 错误消息)。"""
    if limit is None or limit == "":
        return MAX_SUGGESTED_QUESTION_COUNT, None
    try:
        value = int(limit)
    except (TypeError, ValueError):
        return 0, "limit参数必须是整数"
    if value < 1 or value > MAX_SUGGESTED_QUESTION_COUNT:
        return 0, f"limit参数的取值范围为1-{MAX_SUGGESTED_QUESTION_COUNT}"
    return value, None


class MemorySummaryReq(FlaskForm):
    """长期记忆摘要生成请求校验。"""

    human_message = StringField(
        "human_message",
        validators=[
            DataRequired(message="human_message参数必须传递"),
            Length(max=4000, message="human_message最大长度为4000字符"),
        ],
    )
    ai_message = StringField(
        "ai_message",
        validators=[
            DataRequired(message="ai_message参数必须传递"),
            Length(max=4000, message="ai_message最大长度为4000字符"),
        ],
    )
    # 原始摘要允许为空，首次生成时由核心层用占位文案代替
    original_summary = StringField("original_summary", validators=[Optional()])


class ConversationTitleReq(FlaskForm):
    """会话标题生成请求校验。"""

    query = StringField(
        "query",
        validators=[
            DataRequired(message="query参数必须传递"),
            Length(max=2000, message="query参数最大长度为2000字符"),
        ],
    )


class SuggestedQuestionReq(FlaskForm):
    """建议性问题生成请求校验，limit 在 handler 中手动解析。"""

    history = ListField("history", validators=[_validate_history_items])


class ConversationTitleSchema(Schema):
    """会话标题响应拼装。"""

    topic = fields.String()
    language = fields.String()
    reason = fields.String()


__all__ = [
    "MemorySummaryReq",
    "ConversationTitleReq",
    "SuggestedQuestionReq",
    "ConversationTitleSchema",
    "parse_suggested_limit",
    "MAX_HISTORY_MESSAGE_COUNT",
]
