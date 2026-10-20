from uuid import UUID

from flask_wtf import FlaskForm
from marshmallow import Schema, fields
from wtforms import StringField
from wtforms.validators import DataRequired, Length, Optional, ValidationError

from internal.core.agent import DEFAULT_AGENT_LLM

# 视为"开启"的查询参数取值
TRUE_VALUES = ("1", "true", "yes", "on")


def _validate_uuid(form, field) -> None:
    """校验字段值是合法 UUID。"""
    value = field.data
    if not value:
        return
    try:
        UUID(str(value))
    except (TypeError, ValueError):
        raise ValidationError(f"{field.name}参数必须是UUID") from None


def parse_bool(value) -> bool:
    """把查询参数里的字符串解析成布尔值，未传时按关闭处理。"""
    return str(value or "").strip().lower() in TRUE_VALUES


class AgentDebugReq(FlaskForm):
    """工具调用 Agent 调试请求校验，tools 数组在 handler 中用 getlist 读取。"""

    query = StringField(
        "query",
        validators=[
            DataRequired(message="query参数必须传递"),
            Length(max=2000, message="query参数最大长度为2000字符"),
        ],
    )
    app_id = StringField("app_id", validators=[Optional(), _validate_uuid])
    conversation_id = StringField(
        "conversation_id", validators=[Optional(), _validate_uuid]
    )
    llm = StringField("llm", validators=[Optional(), Length(max=255)])
    system_prompt = StringField(
        "system_prompt",
        validators=[Optional(), Length(max=2000, message="system_prompt最大长度2000字符")],
    )
    preset_prompt = StringField(
        "preset_prompt",
        validators=[Optional(), Length(max=2000, message="preset_prompt最大长度2000字符")],
    )
    enable_long_term_memory = StringField("enable_long_term_memory", validators=[Optional()])


class AgentEventSchema(Schema):
    """队列事件响应拼装，用于把 AgentEventEntity 输出给前端。"""

    id = fields.String()
    task_id = fields.String()
    event = fields.String()
    thought = fields.String()
    observation = fields.String()
    tool = fields.String()
    tool_label = fields.String()
    tool_input = fields.Raw()
    message = fields.Raw()
    message_token_count = fields.Integer()
    message_unit_price = fields.Float()
    message_price_unit = fields.Float()
    answer = fields.String()
    answer_token_count = fields.Integer()
    answer_unit_price = fields.Float()
    answer_price_unit = fields.Float()
    total_token_count = fields.Integer()
    total_price = fields.Float()
    latency = fields.Float()


__all__ = [
    "AgentDebugReq",
    "AgentEventSchema",
    "DEFAULT_AGENT_LLM",
    "parse_bool",
    "TRUE_VALUES",
]
