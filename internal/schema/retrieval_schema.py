from flask_wtf import FlaskForm
from marshmallow import Schema, fields
from wtforms import StringField
from wtforms.validators import AnyOf, DataRequired, Optional

from internal.entity import RETRIEVAL_STRATEGIES


class HitTestingReq(FlaskForm):
    """召回测试请求校验；k 与 score 为数值，在 handler 里手动校验。"""

    query = StringField(
        "query",
        validators=[DataRequired(message="query参数必须传递")],
    )
    retrieval_strategy = StringField(
        "retrieval_strategy",
        validators=[
            Optional(),
            AnyOf(
                RETRIEVAL_STRATEGIES,
                message="retrieval_strategy参数无效，仅支持 vector/full_text/hybrid",
            ),
        ],
    )


class RetrievalSegmentSchema(Schema):
    """召回结果里的片段信息。"""

    id = fields.String()
    document_id = fields.String()
    position = fields.Integer()
    content = fields.String()
    keywords = fields.List(fields.String())
    hit_count = fields.Integer()
    enabled = fields.Boolean()
    status = fields.String()


class RetrievalDocumentSchema(Schema):
    """召回结果里的文档信息：名称与上传文件的扩展名、媒体类型。"""

    id = fields.String()
    name = fields.String()
    extension = fields.String()
    mime_type = fields.String()


class RetrievalRecordSchema(Schema):
    """单条召回记录：片段信息 + 文档信息 + 检索分数。"""

    segment = fields.Nested(RetrievalSegmentSchema)
    document = fields.Nested(RetrievalDocumentSchema)
    score = fields.Float()


class DatasetQuerySchema(Schema):
    """知识库检索记录响应拼装。"""

    id = fields.UUID()
    dataset_id = fields.UUID()
    query = fields.String()
    source = fields.String()
    source_app_id = fields.UUID()
    created_by = fields.UUID()
    created_at = fields.DateTime(format="iso")
    updated_at = fields.DateTime(format="iso")


__all__ = [
    "HitTestingReq",
    "RetrievalSegmentSchema",
    "RetrievalDocumentSchema",
    "RetrievalRecordSchema",
    "DatasetQuerySchema",
]
