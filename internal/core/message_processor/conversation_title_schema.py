from pydantic import BaseModel, Field


class ConversationTitle(BaseModel):
    """会话标题生成结果，语言与用户提问保持一致。"""

    topic: str = Field(description="会话主题")
    language: str = Field(description="主题使用的语言类型，如中文、英文、中英混合")
    reason: str = Field(description="生成该主题的理由")


__all__ = ["ConversationTitle"]
