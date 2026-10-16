from flask_wtf import FlaskForm
from marshmallow import Schema, fields
from wtforms import StringField
from wtforms.validators import DataRequired, Length, ValidationError

from internal.entity import MAX_DOCUMENT_BATCH_SIZE, ProcessType
from pkg.paginator import PaginatorReq


def _validate_process_type(form, field):
    """校验处理类型必须是 automatic 或 custom。"""
    if field.data not in (ProcessType.AUTOMATIC, ProcessType.CUSTOM):
        raise ValidationError(
            f"process_type参数必须是{ProcessType.AUTOMATIC}或{ProcessType.CUSTOM}"
        )


class CreateDocumentReq(FlaskForm):
    """创建文档集请求校验，upload_file_ids 和 rule 在 handler 中手动校验。"""

    process_type = StringField(
        "process_type",
        validators=[
            DataRequired(message="process_type参数必须传递"),
            _validate_process_type,
        ],
    )


def validate_upload_file_ids(upload_file_ids: list) -> str | None:
    """校验上传文件 ID 列表，返回错误消息或 None。"""
    if not upload_file_ids or not isinstance(upload_file_ids, list):
        return "upload_file_ids参数必须传递"
    if not all(isinstance(uid, str) for uid in upload_file_ids):
        return "upload_file_ids中的元素必须是字符串"
    unique_ids = list(dict.fromkeys(upload_file_ids))
    if len(unique_ids) > MAX_DOCUMENT_BATCH_SIZE:
        return f"upload_file_ids最多同时提供{MAX_DOCUMENT_BATCH_SIZE}个文件"
    return None


def validate_custom_rule(rule: dict) -> str | None:
    """校验自定义处理规则，返回错误消息或 None。"""
    if not isinstance(rule, dict):
        return "rule参数必须是字典"
    segment = rule.get("segment")
    if not isinstance(segment, dict):
        return "rule.segment参数必须提供"
    separators = segment.get("separators")
    if not isinstance(separators, list) or len(separators) == 0:
        return "rule.segment.separators必须是非空字符串列表"
    if not all(isinstance(s, str) for s in separators):
        return "rule.segment.separators中的元素必须是字符串"
    chunk_size = segment.get("chunk_size")
    if not isinstance(chunk_size, int):
        return "rule.segment.chunk_size必须是整数"
    if chunk_size < 100 or chunk_size > 2000:
        return "rule.segment.chunk_size的取值范围为100-2000"
    chunk_overlap = segment.get("chunk_overlap")
    if not isinstance(chunk_overlap, int):
        return "rule.segment.chunk_overlap必须是整数"
    if chunk_overlap < 0 or chunk_overlap > chunk_size // 2:
        return f"rule.segment.chunk_overlap的取值范围为0-{chunk_size // 2}"
    pre_rules = rule.get("pre_process_rules")
    if not isinstance(pre_rules, list) or len(pre_rules) != 2:
        return "rule.pre_process_rules必须是长度为2的列表"
    expected_ids = {"remove_extra_space", "remove_url_and_email"}
    actual_ids = set()
    for pr in pre_rules:
        if not isinstance(pr, dict):
            return "rule.pre_process_rules中的元素必须是字典"
        pid = pr.get("id")
        enabled = pr.get("enabled")
        if pid not in expected_ids:
            return f"rule.pre_process_rules中不支持的规则id：{pid}"
        if not isinstance(enabled, bool):
            return f"rule.pre_process_rules中{pid}的enabled必须是布尔值"
        actual_ids.add(pid)
    if actual_ids != expected_ids:
        return "rule.pre_process_rules缺少必要的规则项"
    return None


def deduplicate_ids(upload_file_ids: list) -> list:
    """去重并保持顺序。"""
    return list(dict.fromkeys(upload_file_ids))


class DocumentListReq(PaginatorReq):
    """文档分页列表请求校验，分页参数由基类提供。"""

    pass


class UpdateDocumentReq(FlaskForm):
    """修改文档请求校验，目前只支持修改文档标题。"""

    name = StringField(
        "name",
        validators=[
            DataRequired(message="name参数必须传递"),
            Length(max=255, message="name参数最大长度为255字符"),
        ],
    )


class DocumentSchema(Schema):
    """文档响应拼装。"""

    id = fields.UUID()
    account_id = fields.UUID()
    dataset_id = fields.UUID()
    upload_file_id = fields.UUID()
    process_rule_id = fields.UUID()
    batch = fields.String()
    name = fields.String()
    position = fields.Integer()
    character_count = fields.Integer()
    token_count = fields.Integer()
    status = fields.String()
    enabled = fields.Boolean()
    created_at = fields.DateTime(format="iso")
    updated_at = fields.DateTime(format="iso")


class DocumentBatchStatusSchema(Schema):
    """文档批处理状态响应，合并文档与上传文件信息。"""

    id = fields.UUID()
    name = fields.String()
    extension = fields.String(attribute="upload_file.extension")
    mime_type = fields.String(attribute="upload_file.mime_type")
    size = fields.Integer(attribute="upload_file.size")
    created_at = fields.DateTime(format="iso")
    position = fields.Integer()
    segment_count = fields.Integer()
    status = fields.String()
    error = fields.String()
    stopped_at = fields.DateTime(format="iso")
    processing_started_at = fields.DateTime(format="iso")
    parsing_completed_at = fields.DateTime(format="iso")
    splitting_completed_at = fields.DateTime(format="iso")
    completed_segment_count = fields.Integer()


__all__ = [
    "CreateDocumentReq",
    "DocumentBatchStatusSchema",
    "DocumentListReq",
    "DocumentSchema",
    "UpdateDocumentReq",
    "deduplicate_ids",
    "validate_custom_rule",
    "validate_upload_file_ids",
]
