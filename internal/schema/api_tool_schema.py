from flask_wtf import FlaskForm
from marshmallow import Schema, fields
from wtforms import StringField, ValidationError
from wtforms.validators import DataRequired, Length, URL

from internal.schema.schema import ListField
from pkg.paginator import PaginatorReq


class ValidateOpenAPISchema(FlaskForm):
    """校验 OpenAPI 规范字符串请求。"""

    openapi_schema = StringField(
        "openapi_schema",
        validators=[
            DataRequired(message="openapi_schema参数必须传递"),
            Length(max=65536, message="openapi_schema参数最大长度为65536字符"),
        ],
    )


class CreateOpenAPISchema(FlaskForm):
    """创建自定义 API 工具提供商请求校验。"""

    name = StringField(
        "name",
        validators=[
            DataRequired(message="name参数必须传递"),
            Length(min=1, max=64, message="name参数长度为1-64个字符"),
        ],
    )
    icon = StringField(
        "icon",
        validators=[
            DataRequired(message="icon参数必须传递"),
            URL(message="icon参数必须是URL格式的字符串"),
        ],
    )
    openapi_schema = StringField(
        "openapi_schema",
        validators=[
            DataRequired(message="openapi_schema参数必须传递"),
            Length(max=65536, message="openapi_schema参数最大长度为65536字符"),
        ],
    )
    # 请求头是可选的列表参数，允许传递空列表
    headers = ListField("headers", allow_empty=True)

    def validate_headers(self, field: ListField) -> None:
        # 列表类型和空值已由 ListField 校验，这里只检查每一项的结构
        for index, header in enumerate(field.data or [], start=1):
            if not isinstance(header, dict):
                raise ValidationError(f"headers第 {index} 项必须是字典类型")
            if set(header) != {"key", "value"}:
                raise ValidationError(f"headers第 {index} 项必须只包含key和value字段")
            if not isinstance(header["key"], str) or not header["key"]:
                raise ValidationError(f"headers第 {index} 项的key必须是非空字符串")
            if not isinstance(header["value"], str):
                raise ValidationError(f"headers第 {index} 项的value必须是字符串")


class GetApiToolProvidersWithPageReq(PaginatorReq):
    """自定义 API 工具提供商分页查询请求。

    分页参数 current_page / page_size 由 PaginatorReq 提供，
    这里只补充按名字或描述模糊搜索的 search_word。
    """

    search_word = StringField(
        "search_word",
        default="",
        validators=[
            Length(max=64, message="search_word参数最大长度为64个字符"),
        ],
    )


class ToolParamSchema(Schema):
    """接口参数响应拼装。"""

    name = fields.String()
    # 对外字段沿用 openapi 规范的 in，实体属性是 location
    location = fields.String(data_key="in")
    description = fields.String()
    required = fields.Boolean()
    type = fields.String()


class ToolSchema(Schema):
    """工具响应拼装。"""

    name = fields.String()
    description = fields.String()
    url = fields.String()
    method = fields.String()
    parameters = fields.List(fields.Nested(ToolParamSchema))


class OpenAPISchemaResult(Schema):
    """OpenAPI 规范校验结果响应拼装。"""

    server = fields.String()
    description = fields.String()
    tools = fields.List(fields.Nested(ToolSchema))


class ApiToolResult(Schema):
    """数据库中已创建的 API 工具响应拼装。"""

    id = fields.UUID()
    account_id = fields.UUID()
    provider_id = fields.UUID()
    name = fields.String()
    description = fields.String()
    url = fields.String()
    method = fields.String()
    parameters = fields.List(fields.Dict())
    updated_at = fields.DateTime(format="iso")
    created_at = fields.DateTime(format="iso")


class ApiToolProviderResult(Schema):
    """数据库中已创建的 API 工具提供商响应拼装。"""

    id = fields.UUID()
    account_id = fields.UUID()
    name = fields.String()
    icon = fields.String()
    description = fields.String()
    # 模型字段叫 header，对外统一用 headers
    headers = fields.List(fields.Dict(), attribute="header")
    updated_at = fields.DateTime(format="iso")
    created_at = fields.DateTime(format="iso")
    # tools 是模型上的属性，按 provider_id 现查名下的工具
    tools = fields.List(fields.Nested(ApiToolResult))


class ApiToolProviderBriefResult(Schema):
    """提供商的基础信息，工具详情里内嵌它，不返回 openapi_schema。"""

    id = fields.UUID()
    name = fields.String()
    icon = fields.String()
    description = fields.String()
    headers = fields.List(fields.Dict(), attribute="header")
    created_at = fields.DateTime(format="iso")


class ApiToolProviderDetailResult(ApiToolProviderBriefResult):
    """提供商详情，在基础信息之外返回完整的 openapi 规范。"""

    openapi_schema = fields.Dict()


class ApiToolDetailResult(Schema):
    """提供商下指定工具的详情响应拼装。"""

    id = fields.UUID()
    name = fields.String()
    description = fields.String()
    # inputs 就是工具的参数列表，沿用 openapi 规范里的 in 字段
    inputs = fields.List(fields.Dict(), attribute="parameters")
    provider = fields.Nested(ApiToolProviderBriefResult)


class GetApiToolProvidersWithPageResp(Schema):
    """提供商分页列表的单条响应拼装，不返回体积较大的 openapi_schema。"""

    id = fields.UUID()
    name = fields.String()
    icon = fields.String()
    description = fields.String()
    # 模型字段叫 header，对外统一用 headers
    headers = fields.List(fields.Dict(), attribute="header")
    # tools 是模型上的属性，按 provider_id 现查名下的工具
    tools = fields.List(fields.Nested(ApiToolResult))
    created_at = fields.DateTime(format="iso")


__all__ = [
    "ValidateOpenAPISchema",
    "CreateOpenAPISchema",
    "GetApiToolProvidersWithPageReq",
    "GetApiToolProvidersWithPageResp",
    "ToolParamSchema",
    "ToolSchema",
    "OpenAPISchemaResult",
    "ApiToolResult",
    "ApiToolProviderResult",
    "ApiToolProviderBriefResult",
    "ApiToolProviderDetailResult",
    "ApiToolDetailResult",
]
