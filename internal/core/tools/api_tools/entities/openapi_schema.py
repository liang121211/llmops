import json
from enum import Enum
from typing import Any

from internal.core.tools.api_tools.entities.tool_entities import (
    ALLOWED_METHODS,
    ToolEntity,
    ToolParam,
)
from internal.exception import FailException


class ParameterType(str, Enum):
    """openapi 规范里参数支持的类型。"""

    STR = "str"  # 字符串
    INT = "int"  # 整数
    FLOAT = "float"  # 浮点数
    BOOL = "bool"  # 布尔值


class ParameterIn(str, Enum):
    """openapi 规范里参数的位置。"""

    PATH = "path"  # 路径参数
    QUERY = "query"  # 查询参数
    HEADER = "header"  # 请求头参数
    COOKIE = "cookie"  # Cookie 参数
    REQUEST_BODY = "request_body"  # 请求体参数


# 参数类型映射：规范里的 type 字符串 -> 生成 args_schema 时使用的 Python 类型
ParameterTypeMap: dict[str, type] = {
    ParameterType.STR.value: str,
    ParameterType.INT.value: int,
    ParameterType.FLOAT.value: float,
    ParameterType.BOOL.value: bool,
}


class OpenAPISchema:
    """OpenAPI 规范数据，负责校验规范内容并解析出可用工具。"""

    def __init__(self, schema: dict) -> None:
        self.openapi_schema: dict = schema or {}
        self.server: str = ""
        self.description: str = ""
        self.paths: dict = {}
        self.tools: list[ToolEntity] = []

    @classmethod
    def from_content(cls, content: str | dict) -> "OpenAPISchema":
        """解析规范内容并校验，内容不合法时抛出 FailException。"""
        schema = cls._loads(content)
        instance = cls(schema)
        instance.check()
        return instance

    @staticmethod
    def _loads(content: str | dict) -> dict:
        """把字符串规范转成字典，已经不是字典的数据直接报错。"""
        if isinstance(content, dict):
            return content
        try:
            schema = json.loads(content)
        except (TypeError, ValueError) as error:
            raise FailException(f"openapi_schema不是合法的JSON字符串：{error}")
        if not isinstance(schema, dict):
            raise FailException("openapi_schema解析后必须是JSON对象")
        return schema

    def check(self) -> "OpenAPISchema":
        """按规范逐项校验，并把结果组装回实例。"""
        self.server = self.check_server()
        self.description = self.check_description()
        self.tools = self.check_paths()
        return self

    def check_server(self) -> str:
        """校验 server：必须存在且为字符串。"""
        server = self.openapi_schema.get("server")
        if not isinstance(server, str) or not server:
            raise FailException("openapi_schema缺少server字段或server不是字符串")
        return server

    def check_description(self) -> str:
        """校验 description：必须存在且为字符串。"""
        description = self.openapi_schema.get("description")
        if not isinstance(description, str) or not description:
            raise FailException(
                "openapi_schema缺少description字段或description不是字符串"
            )
        return description

    def check_paths(self) -> list[ToolEntity]:
        """校验 paths 的每个端点与请求方式，返回解析出的工具列表。"""
        paths = self.openapi_schema.get("paths")
        if not isinstance(paths, dict):
            raise FailException("openapi_schema缺少paths字段或paths不是字典")

        tools: list[ToolEntity] = []
        for path, methods in paths.items():
            if not isinstance(path, str) or not path.startswith("/"):
                raise FailException(f"paths中的接口路径 {path} 必须以 / 开头")
            if not isinstance(methods, dict):
                raise FailException(f"paths中 {path} 对应的数据必须是字典")
            if not methods:
                raise FailException(f"paths中 {path} 没有配置任何请求方式")
            for method, operation in methods.items():
                if method not in ALLOWED_METHODS:
                    raise FailException(
                        f"{path} 的请求方式 {method} 不被支持，"
                        f"只能是 {list(ALLOWED_METHODS)} 之一"
                    )
                tools.append(self._check_operation(path, method, operation))

        # 校验通过的原始 paths 同步到实例，供业务层继续使用
        self.paths = paths
        # operationId 是工具的唯一标识，整份规范内不允许重复
        seen: set[str] = set()
        for tool in tools:
            if tool.name in seen:
                raise FailException(f"paths中存在重复的operationId：{tool.name}")
            seen.add(tool.name)
        return tools

    def _check_operation(
        self, path: str, method: str, operation: Any
    ) -> ToolEntity:
        """校验单个接口操作：operationId、description、parameters 缺一不可。"""
        if not isinstance(operation, dict):
            raise FailException(f"接口 {path} 的 {method} 配置必须是字典")

        operation_id = operation.get("operationId")
        if not isinstance(operation_id, str) or not operation_id:
            raise FailException(
                f"接口 {path} 的 {method} 缺少operationId或类型不是字符串"
            )

        description = operation.get("description")
        if not isinstance(description, str) or not description:
            raise FailException(
                f"接口 {path} 的 {method} 缺少description或类型不是字符串"
            )

        parameters = self._check_parameters(
            operation_id, operation.get("parameters")
        )
        return ToolEntity(
            name=operation_id,
            description=description,
            url=path,
            method=method,
            parameters=parameters,
        )

    def _check_parameters(
        self, operation_id: str, parameters: Any
    ) -> list[ToolParam]:
        """校验参数列表结构，每个参数必须包含 name/in/description/required/type。"""
        if parameters is None:
            return []
        if not isinstance(parameters, list):
            raise FailException(f"工具 {operation_id} 的parameters必须是列表")

        tool_params: list[ToolParam] = []
        for index, item in enumerate(parameters, start=1):
            if not isinstance(item, dict):
                raise FailException(
                    f"工具 {operation_id} 的第 {index} 个参数配置必须是字典"
                )

            name = item.get("name")
            if not isinstance(name, str) or not name:
                raise FailException(
                    f"工具 {operation_id} 的第 {index} 个参数缺少name或name不是字符串"
                )

            location = self._in_enum(item.get("in"))
            if location is None:
                raise FailException(
                    f"工具 {operation_id} 的参数 {name} 的in取值不合法，"
                    f"只能是 {self._enum_values(ParameterIn)} 之一"
                )

            description = item.get("description")
            if not isinstance(description, str):
                raise FailException(
                    f"工具 {operation_id} 的参数 {name} 缺少description或类型不是字符串"
                )

            required = item.get("required")
            if not isinstance(required, bool):
                raise FailException(
                    f"工具 {operation_id} 的参数 {name} 缺少required或类型不是布尔值"
                )

            param_type = self._type_enum(item.get("type"))
            if param_type is None:
                raise FailException(
                    f"工具 {operation_id} 的参数 {name} 的type取值不合法，"
                    f"只能是 {self._enum_values(ParameterType)} 之一"
                )

            tool_params.append(
                ToolParam(
                    name=name,
                    location=location.value,
                    description=description,
                    required=required,
                    type=param_type.value,
                )
            )
        return tool_params

    @staticmethod
    def _enum_values(enum_cls: type[Enum]) -> list[str]:
        """枚举的全部合法取值，用于拼装报错提示。"""
        return [member.value for member in enum_cls]

    @staticmethod
    def _in_enum(value: Any) -> ParameterIn | None:
        """把规范里的 in 取值转成枚举，不合法时返回 None。"""
        try:
            return ParameterIn(value)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _type_enum(value: Any) -> ParameterType | None:
        """把规范里的 type 取值转成枚举，不合法时返回 None。"""
        try:
            return ParameterType(value)
        except (ValueError, TypeError):
            return None


__all__ = ["ParameterType", "ParameterIn", "ParameterTypeMap", "OpenAPISchema"]
