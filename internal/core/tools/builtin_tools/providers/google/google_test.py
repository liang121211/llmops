from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field


class GoogleTestArgsSchema(BaseModel):
    """测试工具的API参数描述"""

    query: str = Field(description="需要回显的内容")


def google_test(**kwargs) -> BaseTool:
    """测试工具实例化，参数来自 google_test.yml 的 params 配置。"""
    channel = kwargs.get("channel", "web")
    limit = kwargs.get("limit", 3)
    verbose = kwargs.get("verbose", False)
    prefix = kwargs.get("prefix", "demo")

    def _run(query: str) -> str:
        # 回显配置参数，方便验证 YAML 里的参数确实传进了工厂函数
        return f"[{prefix}] channel={channel} limit={limit} verbose={verbose} query={query}"

    return StructuredTool.from_function(
        func=_run,
        name="google_test",
        description="这是一个内置插件的测试工具，用于验证工具配置与参数是否被正确加载.",
        args_schema=GoogleTestArgsSchema,
    )


__all__ = ["GoogleTestArgsSchema", "google_test"]
