from dataclasses import dataclass

import inject
from flask import request
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from werkzeug.datastructures import MultiDict

from internal.core.tools.builtin_tools import BuiltinProviderManager
from internal.pkg.response import (
    not_found_message,
    success_json,
    validate_error_json,
)
from internal.schema.app_schema import AppSchema, CompletionReq
from internal.service.app_service import AppService

# 应用的构建参数全部由服务端给出，调用方不需要传参
APP_NAME = "智能体应用"
APP_ICON = "assistant.png"
APP_CONFIG = {"model": "deepseek-v4-flash", "temperature": 0.7}
UPDATED_APP_NAME = "智能体应用-已更新"
UPDATED_APP_CONFIG = {"model": "deepseek-v4-flash", "temperature": 0.3}


@inject.autoparams()
@dataclass
class AppHandler:
    """应用控制层。"""

    app_service: AppService
    provider_manager: BuiltinProviderManager

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

    def builtin_tool_test(self):
        # 1. 校验请求体中的 query 参数
        payload = request.get_json(silent=True) or {}
        form = CompletionReq(formdata=MultiDict(payload))
        if not form.validate():
            return validate_error_json(form.errors)
        query = form.query.data
        # 2. 从内置插件管理器取 google 服务商的谷歌搜索工具实例
        tool = self.provider_manager.get_tool_instance("google", "google_serper")
        if tool is None:
            return not_found_message("内置工具 google_serper 不可用")
        # 3. 用用户的 query 触发联网检索，结果原样返回
        return success_json({"content": tool.invoke({"query": query})})

    def create_app(self):
        # 新增：由服务端决定应用参数，返回创建后的应用详情
        app = self.app_service.create_app(
            name=APP_NAME, icon=APP_ICON, config=APP_CONFIG
        )
        return success_json({"app": AppSchema().dump(app)})

    def get_apps(self):
        # 查询：返回全部应用列表
        apps = self.app_service.get_apps()
        return success_json({"apps": AppSchema(many=True).dump(apps)})

    def update_app(self):
        # 修改：不接收参数，因此更新最近创建的那个应用
        latest = self.app_service.get_latest_app()
        if latest is None:
            return not_found_message("暂无可更新的应用")
        app = self.app_service.update(
            latest.id, name=UPDATED_APP_NAME, config=UPDATED_APP_CONFIG
        )
        return success_json({"app": AppSchema().dump(app)})

    def delete_app(self):
        # 删除：同样作用于最近创建的那个应用
        latest = self.app_service.get_latest_app()
        if latest is None:
            return not_found_message("暂无可删除的应用")
        # 删除提交后模型实例会被会话清理，先把 id 取出来
        app_id = str(latest.id)
        self.app_service.delete(latest.id)
        return success_json({"id": app_id})


__all__ = ["AppHandler"]
