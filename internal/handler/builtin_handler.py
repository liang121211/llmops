from dataclasses import dataclass

import inject
from flask import Response as FlaskResponse

from internal.pkg.response import not_found_message, success_json
from internal.service.builtin_service import BuiltinService

# svg 图标的响应类型
SVG_MIMETYPE = "image/svg+xml"


@inject.autoparams()
@dataclass
class BuiltinHandler:
    """内置插件控制层，对外提供插件的查询接口。"""

    builtin_service: BuiltinService

    def get_builtin_tools(self):
        # 查询：返回全部服务商及其工具信息
        return success_json(self.builtin_service.get_builtin_tools())

    def get_provider_tool(self, provider_name: str, tool_name: str):
        # 查询：按服务商名和工具名返回指定工具信息
        tool = self.builtin_service.get_provider_tool(provider_name, tool_name)
        if tool is None:
            return not_found_message(f"内置工具 {provider_name}/{tool_name} 不存在")
        return success_json(tool)

    def get_provider_icon(self, provider_name: str):
        # 查询：返回服务商图标的字节数据，前端可直接用于 img 展示
        icon = self.builtin_service.get_provider_icon(provider_name)
        if icon is None:
            return not_found_message(f"提供商 {provider_name} 的图标不存在")
        return FlaskResponse(icon, status=200, mimetype=SVG_MIMETYPE)

    def get_categories(self):
        # 查询：返回插件广场的全部分类信息
        return success_json(self.builtin_service.get_categories())


__all__ = ["BuiltinHandler"]
