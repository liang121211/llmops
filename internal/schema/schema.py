from typing import Any

from werkzeug.datastructures import MultiDict
from wtforms import Field, ValidationError


def json_formdata(payload: dict) -> MultiDict:
    """把 JSON 请求体转成表单数据。

    用键值对模式构造 MultiDict，列表和字典会作为单个条目原样保留，
    自定义的 ListField/DictField 才能判断出参数的真实类型。
    """
    return MultiDict([(key, value) for key, value in (payload or {}).items()])


class ListField(Field):
    """自定义列表字段，flask-wtf 原生字段接收不了 JSON 数组。

    作用：校验对应的请求数据是否非空且为列表类型。
    """

    def __init__(
        self,
        label: str = "",
        validators: Any = None,
        allow_empty: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(label, validators, **kwargs)
        # 可选的列表参数允许传空列表，例如请求头 headers
        self.allow_empty = allow_empty

    def process_formdata(self, valuelist: list) -> None:
        # 请求里没有该字段时 wtforms 也会调用，保持默认值不动
        if not valuelist:
            return
        # 请求里的列表数据作为单个条目存放，取回原始列表
        self.data = valuelist[0]

    def pre_validate(self, form: Any) -> None:
        # 请求没有携带该字段时不校验，由字段默认值和校验器处理
        if not self.raw_data:
            return
        if not isinstance(self.data, list):
            raise ValidationError(f"{self.name}参数必须是列表类型")
        if not self.data and not self.allow_empty:
            raise ValidationError(f"{self.name}参数不能是空列表")


class DictField(Field):
    """自定义字典字段，处理方式与 ListField 一致，用于对象类型的数据。

    作用：校验对应的请求数据是否非空且为字典类型。
    """

    def __init__(
        self,
        label: str = "",
        validators: Any = None,
        allow_empty: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(label, validators, **kwargs)
        self.allow_empty = allow_empty

    def process_formdata(self, valuelist: list) -> None:
        # 请求里没有该字段时 wtforms 也会调用，保持默认值不动
        if not valuelist:
            return
        # 请求里的字典数据作为单个条目存放，取回原始字典
        self.data = valuelist[0]

    def pre_validate(self, form: Any) -> None:
        if not self.raw_data:
            return
        if not isinstance(self.data, dict):
            raise ValidationError(f"{self.name}参数必须是字典类型")
        if not self.data and not self.allow_empty:
            raise ValidationError(f"{self.name}参数不能是空字典")


__all__ = ["DictField", "ListField", "json_formdata"]
