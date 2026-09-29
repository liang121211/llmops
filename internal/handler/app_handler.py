from dataclasses import dataclass

import inject
from flask import request
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from werkzeug.datastructures import MultiDict

from internal.pkg.response import success_json, validate_error_json
from internal.schema.app_schema import CompletionReq


@inject.autoparams()
@dataclass
class AppHandler:
    """应用控制层。"""

    def ping(self):
        return {"ping": "pong"}

    def chat(self):
        # 1. 使用 flask-form 校验 JSON 请求体中的参数
        payload = request.get_json(silent=True) or {}
        form = CompletionReq(formdata=MultiDict(payload))
        if not form.validate():
            return validate_error_json(form.errors)
        query = form.query.data
        # 2. 创建 LangChain 提示词
        prompt = ChatPromptTemplate.from_template("请回答用户的问题：{query}")
        # 3. 创建 langchain-openai 模型，使用 deepseek-v4-flash，API KEY 从环境变量读取
        model = ChatOpenAI(model="deepseek-v4-flash")
        # 4. 构建 LCEL 表达式，输入用户的 query，经输出解析器输出内容
        chain = prompt | model | StrOutputParser()
        content = chain.invoke({"query": query})
        # 5. 返回统一响应
        return success_json({"content": content})


__all__ = ["AppHandler"]
