from flask_wtf import FlaskForm
from marshmallow import Schema, fields
from wtforms import StringField
from wtforms.validators import DataRequired, Length, Optional

from pkg.paginator import PaginatorReq


class CreateDatasetReq(FlaskForm):
    """创建知识库请求校验。"""

    name = StringField(
        "name",
        validators=[
            DataRequired(message="name参数必须传递"),
            Length(max=256, message="name参数最大长度为256字符"),
        ],
    )
    icon = StringField("icon", validators=[Optional()])
    description = StringField(
        "description",
        validators=[
            Optional(),
            Length(max=2048, message="description参数最大长度为2048字符"),
        ],
    )


class UpdateDatasetReq(FlaskForm):
    """修改知识库请求校验。"""

    name = StringField(
        "name",
        validators=[
            Optional(),
            Length(max=256, message="name参数最大长度为256字符"),
        ],
    )
    icon = StringField("icon", validators=[Optional()])
    description = StringField(
        "description",
        validators=[
            Optional(),
            Length(max=2048, message="description参数最大长度为2048字符"),
        ],
    )


class DatasetListReq(PaginatorReq):
    """知识库分页列表请求校验。"""

    pass


class DatasetSchema(Schema):
    """知识库响应拼装，包含统计信息。"""

    id = fields.UUID()
    account_id = fields.UUID()
    name = fields.String()
    icon = fields.String()
    description = fields.String()
    related_app_count = fields.Integer()
    document_count = fields.Integer()
    character_count = fields.Integer()
    updated_at = fields.DateTime(format="iso")
    created_at = fields.DateTime(format="iso")


__all__ = [
    "CreateDatasetReq",
    "UpdateDatasetReq",
    "DatasetListReq",
    "DatasetSchema",
]
