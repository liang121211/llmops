from langchain_community.tools import GoogleSerperRun
from langchain_community.utilities import GoogleSerperAPIWrapper
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field


class GoogleSerperArgsSchema(BaseModel):
    """谷歌搜索的API参数描述"""

    query: str = Field(description="需要检索的问题")


def google_serper(**kwargs) -> BaseTool:
    """谷歌搜索工具实例化，参数来自 google_serper.yml 的 params 配置。"""
    api_wrapper = GoogleSerperAPIWrapper(
        # k 是返回条数，hl 是界面语言，默认值由配置文件提供
        k=kwargs.get("num_results", 5),
        hl=kwargs.get("language", "zh-CN"),
    )
    return GoogleSerperRun(
        name="google_serper",
        description="这是一个低成本的谷歌搜索工具，可以使用该工具搜索内容.",
        api_wrapper=api_wrapper,
        args_schema=GoogleSerperArgsSchema,
    )


__all__ = ["GoogleSerperArgsSchema", "google_serper"]
