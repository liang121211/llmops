from flask_wtf import FlaskForm
from marshmallow import Schema, fields
from wtforms import StringField
from wtforms.validators import DataRequired, Length, Optional


class PingForm(FlaskForm):
    """Ping 请求校验。"""

    token = StringField("token", validators=[Optional()])


class CompletionReq(FlaskForm):
    """对话补全请求校验。"""

    query = StringField(
        "query",
        validators=[
            DataRequired(message="query参数必须传递"),
            Length(max=2000, message="query参数最大长度为2000字符"),
        ],
    )


class PingSchema(Schema):
    """Ping 响应拼装。"""

    message = fields.String()


__all__ = ["PingForm", "PingSchema", "CompletionReq"]
