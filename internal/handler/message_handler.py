from dataclasses import dataclass

import inject
from flask import request

from internal.core.message_processor import MessageProcessor
from internal.pkg.response import fail_message, success_json, validate_error_json
from internal.schema.message_schema import (
    ConversationTitleReq,
    ConversationTitleSchema,
    MemorySummaryReq,
    SuggestedQuestionReq,
    parse_suggested_limit,
)
from internal.schema.schema import json_formdata


@inject.autoparams()
@dataclass
class MessageHandler:
    """AI 消息处理控制层：长期记忆摘要、会话标题生成、建议性问题生成。"""

    message_processor: MessageProcessor

    def generate_memory_summary(self):
        """长期记忆：把最新一轮对话压缩进原始摘要。"""
        # 1. flask-form 校验必传的人类消息与 AI 消息
        payload = request.get_json(silent=True) or {}
        form = MemorySummaryReq(formdata=json_formdata(payload))
        if not form.validate():
            return validate_error_json(form.errors)
        # 2. 交给核心层调用大模型生成摘要
        summary = self.message_processor.generate_memory_summary(
            human_message=form.human_message.data,
            ai_message=form.ai_message.data,
            original_summary=payload.get("original_summary") or "",
        )
        # 3. 返回摘要文本
        return success_json({"summary": summary})

    def generate_conversation_title(self):
        """会话名称生成：根据用户首句提问提炼会话主题。"""
        payload = request.get_json(silent=True) or {}
        form = ConversationTitleReq(formdata=json_formdata(payload))
        if not form.validate():
            return validate_error_json(form.errors)
        # 核心层返回 BaseModel，标题语言与用户提问保持一致
        title = self.message_processor.generate_conversation_title(form.query.data)
        return success_json({"title": ConversationTitleSchema().dump(title)})

    def generate_suggested_questions(self):
        """建议性问题：根据历史对话推测用户接下来最可能提问的问题。"""
        payload = request.get_json(silent=True) or {}
        form = SuggestedQuestionReq(formdata=json_formdata(payload))
        if not form.validate():
            return validate_error_json(form.errors)
        # limit 可能是 JSON 数字， StringField 接不住，单独解析
        limit, error = parse_suggested_limit(payload.get("limit"))
        if error:
            return fail_message(error)
        questions = self.message_processor.generate_suggested_questions(
            form.history.data, limit
        )
        return success_json({"questions": questions})


__all__ = ["MessageHandler"]
