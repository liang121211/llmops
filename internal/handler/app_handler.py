from dataclasses import dataclass
from queue import Queue
import threading

import inject
from flask import current_app, request
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import tools_condition
from werkzeug.datastructures import MultiDict

from internal.core.agent import DEFAULT_AGENT_LLM, AgentConfig
from internal.core.tools.builtin_tools import BuiltinProviderManager
from internal.entity import InvokeFrom
from internal.pkg.response import (
    HttpCode,
    Response,
    not_found_message,
    success_json,
    unified_response,
    validate_error_json,
)
from internal.schema.agent_schema import AgentDebugReq, parse_bool
from internal.schema.app_schema import AppSchema, CompletionReq
from internal.service.agent_service import AgentService
from internal.service.app_service import AppService

# 应用的构建参数全部由服务端给出，调用方不需要传参
APP_NAME = "智能体应用"
APP_ICON = "assistant.png"
APP_CONFIG = {"model": "deepseek-v4-flash", "temperature": 0.7}
UPDATED_APP_NAME = "智能体应用-已更新"
UPDATED_APP_CONFIG = {"model": "deepseek-v4-flash", "temperature": 0.3}
# TODO: 等待授权认证模块完成后从登录态取账号
ACCOUNT_ID = "a666a888-8888-6666-1234-b9d69212aaaa"


@inject.autoparams()
@dataclass
class AppHandler:
    """应用控制层。"""

    app_service: AppService
    provider_manager: BuiltinProviderManager
    agent_service: AgentService

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

    def debug_stream_output(self):
        """LangGraph + Queue + Thread 的 SSE 流式测试接口（逻辑全部内联）。

        后台线程跑 LangGraph 图，各节点把事件投递到共享队列（生产者）；
        主线程生成器从队列取事件逐条产出（消费者），交给统一响应包装成
        text/event-stream 流。事件类型：agent_message（AI 文本）、
        agent_thought（AI 思考/决定调用工具）、agent_action（工具执行）。
        """
        # 测试接口：app_id 与 query 直接来自查询参数，不做表单包装
        app_id = request.args.get("app_id")
        query = request.args.get("query")
        if not query:
            return unified_response(
                Response(code=HttpCode.FAIL, message="query参数必须传递")
            )

        # 动态收集可用工具：gaode/dalle3 服务商一旦注册即自动纳入
        tools = []
        for provider_name, tool_name in [
            ("google", "google_serper"),
            ("gaode", "gaode_weather"),
            ("openai", "dalle3"),
        ]:
            instance = self.provider_manager.get_tool_instance(
                provider_name, tool_name
            )
            if instance is not None:
                tools.append(instance)
        tools_by_name = {tool.name: tool for tool in tools}

        # 队列：图节点线程为生产者，主线程生成器为消费者
        event_queue = Queue()
        # Flask 上下文线程本地，后台线程需重入真实 app 才能访问扩展/配置
        flask_app = current_app._get_current_object()

        model = ChatOpenAI(model="deepseek-v4-flash", streaming=True)
        bound_model = model.bind_tools(tools) if tools else model

        # ── LangGraph 节点：AI 节点（流式产出 agent_message）──
        def agent_node(state):
            final = None
            for chunk in bound_model.stream(state["messages"]):
                if chunk.content:
                    event_queue.put({
                        "event": "agent_message",
                        "data": {"text": chunk.content},
                    })
                final = chunk if final is None else final + chunk
            if final is None:
                final = AIMessage("")
            # 需要调用工具时先播报思考过程
            for call in (final.tool_calls or []):
                event_queue.put({
                    "event": "agent_thought",
                    "data": {
                        "thought": f"需要调用工具 {call['name']}",
                        "tool": call["name"],
                        "tool_input": call["args"],
                    },
                })
            return {"messages": [final]}

        # ── LangGraph 节点：工具节点（执行并产出 agent_action）──
        def tool_node(state):
            last = state["messages"][-1]
            outputs = []
            for call in (last.tool_calls or []):
                tool = tools_by_name.get(call["name"])
                try:
                    result = (
                        tool.invoke(call["args"])
                        if tool is not None
                        else f"未找到工具 {call['name']}"
                    )
                except Exception as error:
                    result = f"工具调用失败：{error}"
                event_queue.put({
                    "event": "agent_action",
                    "data": {
                        "tool": call["name"],
                        "tool_input": call["args"],
                        "observation": str(result)[:1000],
                    },
                })
                outputs.append(
                    ToolMessage(
                        content=str(result),
                        tool_call_id=call.get("id"),
                        name=call["name"],
                    )
                )
            return {"messages": outputs}

        # ── 路由：有 tool_calls 去工具节点，否则结束（形成 AI↔工具 循环）──
        graph = StateGraph(MessagesState)
        graph.add_node("agent", agent_node)
        graph.add_node("tools", tool_node)
        graph.add_edge(START, "agent")
        graph.add_conditional_edges(
            "agent", tools_condition, {"tools": "tools", END: END}
        )
        graph.add_edge("tools", "agent")
        compiled = graph.compile()

        # 生产者线程：执行整张图，节点内把事件写入队列，结束后放哨兵
        def produce():
            with flask_app.app_context():
                try:
                    compiled.invoke(
                        {"messages": [HumanMessage(query)]},
                        config={"recursion_limit": 12},
                    )
                except Exception as error:
                    event_queue.put({
                        "event": "agent_message",
                        "data": {"error": str(error)},
                    })
                finally:
                    event_queue.put(None)

        thread = threading.Thread(target=produce, daemon=True)
        thread.start()

        # 消费者生成器：逐条取出事件并补上 app_id，None 哨兵表示流结束
        def consume():
            while True:
                item = event_queue.get()
                if item is None:
                    break
                item["app_id"] = str(app_id) if app_id else None
                yield item

        return unified_response(consume())

    def debug_agent(self):
        """工具调用 Agent 调试接口：LangGraph + Queue + Thread + Redis，SSE 输出。

        参数（全部走查询字符串）：query 必填；app_id / conversation_id 可选 UUID；
        llm / system_prompt / preset_prompt 配置模型与提示词；
        enable_long_term_memory=true 开启长期记忆；tools 可重复传工具名。
        """
        # 1. flask-form 校验查询参数
        form = AgentDebugReq(formdata=request.args)
        if not form.validate():
            return validate_error_json(form.errors)
        # 2. 按入参拼装智能体配置，tools 支持 tools=a&tools=b 重复键

        config = AgentConfig(
            llm=form.llm.data or DEFAULT_AGENT_LLM,
            system_prompt=form.system_prompt.data or "",
            preset_prompt=form.preset_prompt.data or "",
            enable_long_term_memory=parse_bool(form.enable_long_term_memory.data),
            tools=[name for name in request.args.getlist("tools") if name],
        )
        # 3. 服务层建会话、起线程执行智能体，返回事件流
        stream = self.agent_service.debug_stream(
            query=form.query.data,
            config=config,
            account_id=ACCOUNT_ID,
            app_id=form.app_id.data or None,
            conversation_id=form.conversation_id.data or None,
            invoke_from=InvokeFrom.DEBUGGER,
        )
        # 4. 生成器交给统一响应，输出 text/event-stream
        return unified_response(stream)

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
