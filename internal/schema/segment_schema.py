from flask_wtf import FlaskForm
from marshmallow import Schema, fields
from wtforms import StringField
from wtforms.validators import DataRequired

from pkg.paginator import PaginatorReq


class SegmentListReq(PaginatorReq):
    """片段分页列表请求校验，分页参数由基类提供。"""

    pass


class CreateSegmentReq(FlaskForm):
    """新增片段请求校验，keywords 为 JSON 列表需在 handler 中手动校验。"""

    content = StringField(
        "content",
        validators=[DataRequired(message="content参数必须传递")],
    )


class UpdateSegmentReq(FlaskForm):
    """修改片段请求校验，content 与 keywords 都要求显式提供。"""

    content = StringField(
        "content",
        validators=[DataRequired(message="content参数必须传递")],
    )


def validate_segment_keywords(keywords) -> tuple[list[str], str | None]:
    """校验关键词列表，返回 (规范化列表, 错误消息)；错误时列表为空。"""
    if keywords is None:
        return [], None
    if not isinstance(keywords, list):
        return [], "keywords参数必须是字符串列表"
    if not all(isinstance(kw, str) for kw in keywords):
        return [], "keywords中的元素必须是字符串"
    # 去重并保持顺序
    return list(dict.fromkeys(keywords)), None


class SegmentSchema(Schema):
    """片段响应拼装。"""

    id = fields.UUID()
    account_id = fields.UUID()
    dataset_id = fields.UUID()
    document_id = fields.UUID()
    node_id = fields.String()
    position = fields.Integer()
    content = fields.String()
    character_count = fields.Integer()
    token_count = fields.Integer()
    keywords = fields.List(fields.String())
    hit_count = fields.Integer()
    enabled = fields.Boolean()
    status = fields.String()
    created_at = fields.DateTime(format="iso")
    updated_at = fields.DateTime(format="iso")


__all__ = [
    "CreateSegmentReq",
    "SegmentListReq",
    "SegmentSchema",
    "UpdateSegmentReq",
    "validate_segment_keywords",
]
