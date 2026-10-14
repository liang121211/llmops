from dataclasses import dataclass

import inject
from flask import request
from pydantic import ValidationError

from internal.pkg.response import not_found_message, success_json, validate_error_json
from internal.schema.api_tool_schema import (
    ApiToolDetailResult,
    ApiToolProviderDetailResult,
    ApiToolProviderResult,
    CreateOpenAPISchema,
    GetApiToolProvidersWithPageReq,
    GetApiToolProvidersWithPageResp,
    OpenAPISchemaResult,
    ValidateOpenAPISchema,
)
from internal.schema.schema import json_formdata
from internal.service.api_tool_service import ApiToolService


@inject.autoparams()
@dataclass
class ApiToolHandler:
    """API 工具控制层，对外提供第三方 API 工具相关接口。"""

    api_tool_service: ApiToolService

    def validate_openapi_schema(self):
        # 1. 使用 flask-form 校验 JSON 请求体中的规范字符串
        payload = request.get_json(silent=True) or {}
        form = ValidateOpenAPISchema(formdata=json_formdata(payload))
        if not form.validate():
            return validate_error_json(form.errors)
        # 2. 交给服务层解析校验，规范不合法会抛出异常由全局异常处理返回
        schema = self.api_tool_service.load_openapi_schema(form.openapi_schema.data)
        # 3. 用 marshmallow 拼装解析结果
        return success_json(OpenAPISchemaResult().dump(schema))

    def create_openapi_schema(self):
        # TODO: 等待授权认证模块完成后再进行切换调整
        account_id = "a666a888-8888-6666-1234-b9d69212aaaa"
        # 1. 校验创建请求的参数，列表类型的 headers 交给自定义字段处理
        payload = request.get_json(silent=True) or {}
        form = CreateOpenAPISchema(formdata=json_formdata(payload))
        if not form.validate():
            return validate_error_json(form.errors)
        # 2. 服务层解析规范，并把提供商与工具数据一起入库
        provider = self.api_tool_service.create_openapi_schema(
            account_id=account_id,
            name=form.name.data,
            icon=form.icon.data,
            openapi_schema=form.openapi_schema.data,
            headers=form.headers.data,
        )
        # 3. 返回创建好的提供商及其名下的工具
        return success_json(ApiToolProviderResult().dump(provider))

    def invoke_tool(self, provider_id, tool_name: str):
        # TODO: 等待授权认证模块完成后再进行切换调整
        account_id = "a666a888-8888-6666-1234-b9d69212aaaa"
        # 1. 工具入参由规范动态决定，没有固定的表单可校验，这里只要求请求体是 JSON 对象
        payload = request.get_json(silent=True) or {}
        if not isinstance(payload, dict):
            return validate_error_json({"args": ["请求体必须是JSON对象"]})
        # 2. 取出包装好的工具，没有对应数据时按资源不存在返回
        tool = self.api_tool_service.get_tool_instance(
            account_id, provider_id, tool_name
        )
        if tool is None:
            return not_found_message(f"API工具 {provider_id}/{tool_name} 不存在")
        # 3. 调用工具向第三方接口发起真实请求，入参交给 args_schema 校验
        try:
            result = tool.invoke(payload)
        except ValidationError as error:
            messages = [
                f"{'.'.join(str(part) for part in item['loc'])} {item['msg']}"
                for item in error.errors()
            ]
            return validate_error_json({"args": messages})
        return success_json({"result": result})

    def get_providers_with_page(self):
        # TODO: 等待授权认证模块完成后再进行切换调整
        account_id = "a666a888-8888-6666-1234-b9d69212aaaa"
        # 1. 分页与搜索参数都来自查询字符串，交给基础分页表单校验
        form = GetApiToolProvidersWithPageReq(formdata=request.args)
        if not form.validate():
            return validate_error_json(form.errors)
        # 2. 分页查询当前账号下的提供商
        page = self.api_tool_service.get_providers_with_page(
            account_id, form, search_word=form.search_word.data.strip()
        )
        # 3. 列表数据用 marshmallow 裁剪字段，分页器直接转成字典
        return success_json(page.dump(GetApiToolProvidersWithPageResp()))

    def get_provider(self, provider_id):
        # TODO: 等待授权认证模块完成后再进行切换调整
        account_id = "a666a888-8888-6666-1234-b9d69212aaaa"
        # 查询：返回指定提供商的详情，包含完整的 openapi 规范
        provider = self.api_tool_service.get_provider_by_id(account_id, provider_id)
        if provider is None:
            return not_found_message(f"API工具提供商 {provider_id} 不存在")
        return success_json(ApiToolProviderDetailResult().dump(provider))

    def get_tool(self, provider_id, tool_name: str):
        # TODO: 等待授权认证模块完成后再进行切换调整
        account_id = "a666a888-8888-6666-1234-b9d69212aaaa"
        # 查询：返回提供商下指定名字的工具，provider 里不带 openapi 规范
        tool = self.api_tool_service.get_tool(account_id, provider_id, tool_name)
        if tool is None:
            return not_found_message(f"API工具 {provider_id}/{tool_name} 不存在")
        return success_json(ApiToolDetailResult().dump(tool))

    def delete_provider(self, provider_id):
        # TODO: 等待授权认证模块完成后再进行切换调整
        account_id = "a666a888-8888-6666-1234-b9d69212aaaa"
        # 删除：提供商与其名下的工具一起删除
        if not self.api_tool_service.delete_provider(account_id, provider_id):
            return not_found_message(f"API工具提供商 {provider_id} 不存在")
        return success_json({"id": str(provider_id)})


__all__ = ["ApiToolHandler"]
