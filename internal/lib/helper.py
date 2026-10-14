import importlib
from datetime import datetime, timezone
from typing import Any

import yaml


def utc_now():
    """返回当前 UTC 时间。"""
    return datetime.now(timezone.utc)


def dynamic_import(module_name: str, symbol_name: str) -> Any:
    """动态导入特定模块下的特定功能"""
    module = importlib.import_module(module_name)
    if not hasattr(module, symbol_name):
        raise ImportError(f"模块 {module_name} 中不存在 {symbol_name}")
    return getattr(module, symbol_name)


def load_yaml(file_path: str) -> Any:
    """读取 YAML 配置，Windows 下必须显式指定 UTF-8，否则中文配置会乱码。"""
    with open(file_path, encoding="utf-8") as file:
        return yaml.safe_load(file)


__all__ = ["utc_now", "dynamic_import", "load_yaml"]
