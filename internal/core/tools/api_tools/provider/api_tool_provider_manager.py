from collections import defaultdict
from typing import Any, Callable

import requests
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field, create_model

from internal.core.tools.api_tools.entities.openapi_schema import (
    ParameterIn,
    ParameterTypeMap,
)
from internal.core.tools.api_tools.entities.tool_entities import ToolEntity, ToolParam

# 第三方接口的超时时间（秒），避免请求一直挂着占住工作线程
REQUEST_TIMEOUT = 30
# 动态生成的入参模型统一用这个名字，pydantic 的报错提示里会出现它
ARGS_SCHEMA_NAME = "ApiToolArgsSchema"


class ApiProviderManager:
    """自定义 API 工具管理器。

    用户创建的提供商与工具最终都落在数据库里，
    这里负责把工具实体包装成 LangChain 可以直接调用的 BaseTool。
    """

    def get_tool(
        self, tool_entity: ToolEntity, headers: dict | None = None
    ) -> BaseTool:
        """把工具实体包装成 BaseTool，入参协议与请求函数都是动态生成的。"""
        return StructuredTool.from_function(
            func=self._generate_func(tool_entity, headers or {}),
            name=tool_entity.name,
            description=tool_entity.description,
            args_schema=self._generate_args_schema(tool_entity.parameters),
        )

    def _generate_args_schema(self, parameters: list[ToolParam]) -> type[BaseModel]:
        """按参数列表动态创建 BaseModel 子类，作为 BaseTool 的 args_schema。

        类型取自 ParameterTypeMap，必填参数没有默认值，选填参数允许不传。
        """
        fields: dict[str, Any] = {}
        for param in parameters:
            param_type = ParameterTypeMap.get(param.type, str)
            description = param.description or param.name
            if param.required:
                fields[param.name] = (param_type, Field(description=description))
            else:
                fields[param.name] = (
                    param_type | None,
                    Field(default=None, description=description),
                )
        return create_model(ARGS_SCHEMA_NAME, **fields)

    def _generate_func(self, tool_entity: ToolEntity, headers: dict) -> Callable:
        """按工具实体生成一个使用 requests 发起真实 API 请求的函数。

        参数按规范里的 in 分别拼到路径、查询字符串、请求头、Cookie 和请求体上，
        headers 是提供商上配置的固定请求头。
        """
        locations = self._locations(tool_entity.parameters)
        url = tool_entity.url
        method = tool_entity.method

        def func(**kwargs: Any) -> str:
            # 路径参数直接替换 url 里的 {name} 占位符
            request_url = url
            for name in locations[ParameterIn.PATH.value]:
                value = str(kwargs.get(name, ""))
                request_url = request_url.replace(f"{{{name}}}", value)
            # 调用时传入的请求头优先级更高，可以覆盖提供商上的配置
            request_headers = dict(headers)
            request_headers.update(
                self._values(kwargs, locations[ParameterIn.HEADER.value])
            )
            body = self._values(kwargs, locations[ParameterIn.REQUEST_BODY.value])
            response = requests.request(
                method,
                request_url,
                params=self._values(kwargs, locations[ParameterIn.QUERY.value]),
                headers=request_headers,
                cookies=self._values(kwargs, locations[ParameterIn.COOKIE.value]),
                # 没有请求体参数时不能传空字典，否则 GET 也会带上 JSON 体
                json=body or None,
                timeout=REQUEST_TIMEOUT,
            )
            # 上游返回 4xx/5xx 时抛出异常，由全局异常处理统一响应
            response.raise_for_status()
            return response.text

        return func

    @staticmethod
    def _locations(parameters: list[ToolParam]) -> dict[str, list[str]]:
        """把参数名按 openapi 规范里的 in 分组，取值时不必每次遍历整个列表。"""
        grouped: dict[str, list[str]] = defaultdict(list)
        for param in parameters:
            grouped[param.location].append(param.name)
        return grouped

    @staticmethod
    def _values(kwargs: dict, names: list[str]) -> dict:
        """挑出本次调用真正传了值的参数，没传的不参与请求拼装。"""
        return {name: kwargs[name] for name in names if kwargs.get(name) is not None}


__all__ = ["ARGS_SCHEMA_NAME", "REQUEST_TIMEOUT", "ApiProviderManager"]
