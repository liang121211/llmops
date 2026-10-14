from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ToolParamType(str, Enum):
    """工具参数类型，与工具配置文件中 params.type 的取值一一对应。"""

    STRING = "string"  # 字符串
    NUMBER = "number"  # 数字
    BOOL = "bool"  # 布尔值
    SELECT = "select"  # 下拉选择列表


@dataclass
class ToolParam:
    """工具参数，对应工具配置文件中 params 的一条定义。"""

    name: str = ""  # 参数名，同时作为工厂函数的关键字参数
    generate_name: str = ""  # 展示给大模型/前端的参数名，缺省时与 name 相同
    desc: str = ""  # 参数说明
    type: ToolParamType = ToolParamType.STRING  # 参数类型
    required: bool = False  # 是否必填
    default: Any = None  # 默认值
    min_value: Any = None  # 数字类型的最小值
    max_value: Any = None  # 数字类型的最大值
    options: list[Any] = field(default_factory=list)  # 下拉选项菜单列表

    @classmethod
    def from_config(cls, config: dict) -> "ToolParam":
        """把 YAML 里的一条参数配置转成实体。"""
        param_type = ToolParamType(config.get("type", ToolParamType.STRING.value))
        return cls(
            name=config.get("name", ""),
            generate_name=config.get("generate_name") or config.get("name", ""),
            desc=config.get("desc", ""),
            type=param_type,
            required=bool(config.get("required", False)),
            default=config.get("default"),
            min_value=config.get("min"),
            max_value=config.get("max"),
            options=list(config.get("options") or []),
        )

    def normalize(self, value: Any = None) -> Any:
        """整理外部传入的取值：空值回落默认值，数字按最小最大值裁剪。"""
        if value is None:
            return self.default
        if self.type == ToolParamType.NUMBER:
            try:
                number = float(value)
            except (TypeError, ValueError):
                return self.default
            if self.min_value is not None:
                number = max(number, float(self.min_value))
            if self.max_value is not None:
                number = min(number, float(self.max_value))
            return int(number) if number.is_integer() else number
        if self.type == ToolParamType.BOOL:
            return bool(value)
        return value

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "generate_name": self.generate_name,
            "desc": self.desc,
            "type": self.type.value,
            "required": self.required,
            "default": self.default,
            "min": self.min_value,
            "max": self.max_value,
            "options": list(self.options),
        }


@dataclass
class ToolEntity:
    """工具实体，对应工具名.yml 的全部内容。"""

    name: str = ""
    label: str = ""
    description: str = ""
    params: list[ToolParam] = field(default_factory=list)

    @classmethod
    def from_config(cls, config: dict) -> "ToolEntity":
        """把工具 YAML 配置转成实体。"""
        return cls(
            name=config.get("name", ""),
            label=config.get("label", ""),
            description=config.get("description", ""),
            params=[
                ToolParam.from_config(item) for item in (config.get("params") or [])
            ],
        )

    def get_param(self, name: str) -> ToolParam | None:
        """按参数名查找参数定义。"""
        return next((param for param in self.params if param.name == name), None)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "label": self.label,
            "description": self.description,
            "params": [param.to_dict() for param in self.params],
        }


__all__ = ["ToolParamType", "ToolParam", "ToolEntity"]
