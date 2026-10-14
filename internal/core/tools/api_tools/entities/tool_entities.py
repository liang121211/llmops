from dataclasses import dataclass, field

# openapi 规范里接口支持的请求方式，只允许 get 与 post
ALLOWED_METHODS = ("get", "post")


@dataclass
class ToolParam:
    """接口参数，对应 openapi 规范 parameters 里的一条定义。"""

    name: str = ""  # 参数名
    location: str = ""  # 参数位置，取值来自 ParameterIn 枚举
    description: str = ""  # 参数说明
    required: bool = False  # 是否必填
    type: str = ""  # 参数类型，取值来自 ParameterType 枚举

    def to_dict(self) -> dict:
        # 对外仍按 openapi 规范的 in 字段暴露参数位置
        return {
            "name": self.name,
            "in": self.location,
            "description": self.description,
            "required": self.required,
            "type": self.type,
        }


@dataclass
class ToolEntity:
    """工具描述，一个接口路径加一种请求方式就是一个工具。"""

    name: str = ""  # 工具名字，取接口唯一标识 operationId
    description: str = ""  # 工具描述
    url: str = ""  # 接口路径，形如 /suggest
    method: str = ""  # 请求方式，get 或 post
    parameters: list[ToolParam] = field(default_factory=list)  # 工具参数列表

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "url": self.url,
            "method": self.method,
            "parameters": [param.to_dict() for param in self.parameters],
        }


__all__ = ["ALLOWED_METHODS", "ToolParam", "ToolEntity"]
