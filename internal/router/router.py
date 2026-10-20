from dataclasses import dataclass

import inject
from flask import Blueprint, Flask

from internal.handler.api_tool_handler import ApiToolHandler
from internal.handler.app_handler import AppHandler
from internal.handler.builtin_handler import BuiltinHandler
from internal.handler.celery_handler import CeleryHandler
from internal.handler.dataset_handler import DatasetHandler
from internal.handler.document_handler import DocumentHandler
from internal.handler.keyword_handler import KeywordHandler
from internal.handler.message_handler import MessageHandler
from internal.handler.oauth_handler import OAuthHandler
from internal.handler.upload_file_handler import UploadFileHandler


@inject.autoparams()
@dataclass
class Router:
    """路由层，通过注入拿到控制层并挂到 Flask 蓝图上。"""

    app_handler: AppHandler
    builtin_handler: BuiltinHandler
    api_tool_handler: ApiToolHandler
    upload_file_handler: UploadFileHandler
    celery_handler: CeleryHandler
    dataset_handler: DatasetHandler
    document_handler: DocumentHandler
    keyword_handler: KeywordHandler
    message_handler: MessageHandler
    oauth_handler: OAuthHandler

    def register_router(self, app: Flask):
        bp = Blueprint("app", __name__)

        # ── 健康检查 ──────────────────────────────────────────────
        bp.add_url_rule("/ping", view_func=self.app_handler.ping, methods=["GET"])

        # ── 应用管理 ──────────────────────────────────────────────
        bp.add_url_rule(
            "/app/chat", view_func=self.app_handler.chat, methods=["POST"]
        )
        bp.add_url_rule(
            "/app/builtin_tool_test",
            view_func=self.app_handler.builtin_tool_test,
            methods=["POST"],
        )
        # 应用的增删改查共用 /app 资源路径，用请求方法区分操作
        bp.add_url_rule(
            "/app", view_func=self.app_handler.create_app, methods=["POST"]
        )
        bp.add_url_rule(
            "/app", view_func=self.app_handler.get_apps, methods=["GET"]
        )
        bp.add_url_rule(
            "/app", view_func=self.app_handler.update_app, methods=["PUT"]
        )
        bp.add_url_rule(
            "/app", view_func=self.app_handler.delete_app, methods=["DELETE"]
        )

        # ── 内置插件 ──────────────────────────────────────────────
        bp.add_url_rule(
            "/builtin-tools",
            view_func=self.builtin_handler.get_builtin_tools,
            methods=["GET"],
        )
        bp.add_url_rule(
            "/builtin-tools/categories",
            view_func=self.builtin_handler.get_categories,
            methods=["GET"],
        )
        bp.add_url_rule(
            "/builtin-tools/<string:provider_name>/icon",
            view_func=self.builtin_handler.get_provider_icon,
            methods=["GET"],
        )
        bp.add_url_rule(
            "/builtin-tools/<string:provider_name>/tools/<string:tool_name>",
            view_func=self.builtin_handler.get_provider_tool,
            methods=["GET"],
        )

        # ── 第三方 API 工具 ───────────────────────────────────────
        bp.add_url_rule(
            "/api-tools/validate-openapi-schema",
            view_func=self.api_tool_handler.validate_openapi_schema,
            methods=["POST"],
        )
        bp.add_url_rule(
            "/api-tools",
            view_func=self.api_tool_handler.create_openapi_schema,
            methods=["POST"],
        )
        bp.add_url_rule(
            "/api-tools",
            view_func=self.api_tool_handler.get_providers_with_page,
            methods=["GET"],
        )
        bp.add_url_rule(
            "/api-tools/invoke/<uuid:provider_id>/<string:tool_name>",
            view_func=self.api_tool_handler.invoke_tool,
            methods=["POST"],
        )
        bp.add_url_rule(
            "/api-tools/<uuid:provider_id>",
            view_func=self.api_tool_handler.get_provider,
            methods=["GET"],
        )
        bp.add_url_rule(
            "/api-tools/<uuid:provider_id>",
            view_func=self.api_tool_handler.delete_provider,
            methods=["DELETE"],
        )
        bp.add_url_rule(
            "/api-tools/<uuid:provider_id>/tools/<string:tool_name>",
            view_func=self.api_tool_handler.get_tool,
            methods=["GET"],
        )

        # ── 文件上传 ──────────────────────────────────────────────
        bp.add_url_rule(
            "/upload-files/file",
            view_func=self.upload_file_handler.upload_file,
            methods=["POST"],
        )
        bp.add_url_rule(
            "/upload-files/image",
            view_func=self.upload_file_handler.upload_image,
            methods=["POST"],
        )

        # ── 文档加载 ──────────────────────────────────────────────
        bp.add_url_rule(
            "/document/<uuid:upload_file_id>/load",
            view_func=self.document_handler.load_document,
            methods=["GET"],
        )

        # ── 知识库 ────────────────────────────────────────────────
        bp.add_url_rule(
            "/datasets",
            view_func=self.dataset_handler.create_dataset,
            methods=["POST"],
        )
        bp.add_url_rule(
            "/datasets",
            view_func=self.dataset_handler.get_datasets,
            methods=["GET"],
        )
        bp.add_url_rule(
            "/datasets/<uuid:dataset_id>",
            view_func=self.dataset_handler.get_dataset,
            methods=["GET"],
        )
        bp.add_url_rule(
            "/datasets/<uuid:dataset_id>",
            view_func=self.dataset_handler.update_dataset,
            methods=["PUT"],
        )
        bp.add_url_rule(
            "/datasets/<uuid:dataset_id>",
            view_func=self.dataset_handler.delete_dataset,
            methods=["DELETE"],
        )
        # 知识库文档：创建文档集
        bp.add_url_rule(
            "/datasets/<uuid:dataset_id>/documents",
            view_func=self.dataset_handler.create_documents,
            methods=["POST"],
        )
        # 知识库文档：获取批次处理状态
        bp.add_url_rule(
            "/datasets/<uuid:dataset_id>/documents/batch/<string:batch_id>",
            view_func=self.dataset_handler.get_batch_status,
            methods=["GET"],
        )
        # 知识库文档：分页查询文档列表（与创建共用资源路径，用方法区分）
        bp.add_url_rule(
            "/datasets/<uuid:dataset_id>/documents",
            view_func=self.dataset_handler.get_documents,
            methods=["GET"],
        )
        # 知识库文档：根据 ID 查询单个文档
        bp.add_url_rule(
            "/datasets/<uuid:dataset_id>/documents/<uuid:document_id>",
            view_func=self.dataset_handler.get_document,
            methods=["GET"],
        )
        # 知识库文档：修改文档（目前仅支持标题）
        bp.add_url_rule(
            "/datasets/<uuid:dataset_id>/documents/<uuid:document_id>",
            view_func=self.dataset_handler.update_document,
            methods=["PUT"],
        )
        # 知识库文档：删除（与查询/修改共用路径，用方法区分）
        bp.add_url_rule(
            "/datasets/<uuid:dataset_id>/documents/<uuid:document_id>",
            view_func=self.dataset_handler.delete_document,
            methods=["DELETE"],
        )
        # 知识库文档：禁用
        bp.add_url_rule(
            "/datasets/<uuid:dataset_id>/documents/<uuid:document_id>/disable",
            view_func=self.dataset_handler.disable_document,
            methods=["PUT"],
        )
        # 知识库文档：启用
        bp.add_url_rule(
            "/datasets/<uuid:dataset_id>/documents/<uuid:document_id>/enable",
            view_func=self.dataset_handler.enable_document,
            methods=["PUT"],
        )

        # 知识库片段：分页列表与新增共用资源路径
        bp.add_url_rule(
            "/datasets/<uuid:dataset_id>/documents/<uuid:document_id>/segments",
            view_func=self.dataset_handler.get_segments,
            methods=["GET"],
        )
        bp.add_url_rule(
            "/datasets/<uuid:dataset_id>/documents/<uuid:document_id>/segments",
            view_func=self.dataset_handler.create_segment,
            methods=["POST"],
        )
        # 知识库片段：单条查询/修改/删除
        bp.add_url_rule(
            "/datasets/<uuid:dataset_id>/documents/<uuid:document_id>/segments/<uuid:segment_id>",
            view_func=self.dataset_handler.get_segment,
            methods=["GET"],
        )
        bp.add_url_rule(
            "/datasets/<uuid:dataset_id>/documents/<uuid:document_id>/segments/<uuid:segment_id>",
            view_func=self.dataset_handler.update_segment,
            methods=["PUT"],
        )
        bp.add_url_rule(
            "/datasets/<uuid:dataset_id>/documents/<uuid:document_id>/segments/<uuid:segment_id>",
            view_func=self.dataset_handler.delete_segment,
            methods=["DELETE"],
        )
        # 知识库片段：禁用/启用
        bp.add_url_rule(
            "/datasets/<uuid:dataset_id>/documents/<uuid:document_id>/segments/<uuid:segment_id>/disable",
            view_func=self.dataset_handler.disable_segment,
            methods=["PUT"],
        )
        bp.add_url_rule(
            "/datasets/<uuid:dataset_id>/documents/<uuid:document_id>/segments/<uuid:segment_id>/enable",
            view_func=self.dataset_handler.enable_segment,
            methods=["PUT"],
        )

        # ── 检索召回 ────────────────────────────────────────────────
        # 知识库召回测试
        bp.add_url_rule(
            "/datasets/<uuid:dataset_id>/hit-testing",
            view_func=self.dataset_handler.hit_testing,
            methods=["POST"],
        )
        # 知识库：查询最近的检索记录
        bp.add_url_rule(
            "/datasets/<uuid:dataset_id>/queries",
            view_func=self.dataset_handler.get_dataset_queries,
            methods=["GET"],
        )
        # 流式响应测试：GET 请求，返回 SSE 事件流
        bp.add_url_rule(
            "/app/debug_stream",
            view_func=self.app_handler.debug_stream_output,
            methods=["GET"],
        )
        # 工具调用 Agent 调试：GET 请求，按用户输入与配置执行智能体并 SSE 返回事件
        bp.add_url_rule(
            "/app/agent_debug",
            view_func=self.app_handler.debug_agent,
            methods=["GET"],
        )
        # ── 关键词提取 ──────────────────────────────────────────────
        bp.add_url_rule(
            "/keywords/extract",
            view_func=self.keyword_handler.extract,
            methods=["POST"],
        )

        # ── AI 消息处理 ────────────────────────────────────────────
        # 长期记忆：把最新一轮用户与 AI 的消息压缩进原始摘要
        bp.add_url_rule(
            "/messages/memory-summary",
            view_func=self.message_handler.generate_memory_summary,
            methods=["POST"],
        )
        # 会话名称：根据用户首句提问生成与用户语言一致的会话主题
        bp.add_url_rule(
            "/messages/conversation-title",
            view_func=self.message_handler.generate_conversation_title,
            methods=["POST"],
        )
        # 建议性问题：根据历史对话推测用户接下来最想问的问题，最多 3 个
        bp.add_url_rule(
            "/messages/suggested-questions",
            view_func=self.message_handler.generate_suggested_questions,
            methods=["POST"],
        )

        # ── 异步任务 ──────────────────────────────────────────────
        bp.add_url_rule(
            "/celery/demo_task",
            view_func=self.celery_handler.create_demo_task,
            methods=["POST"],
        )
        bp.add_url_rule(
            "/celery/demo_task",
            view_func=self.celery_handler.get_demo_task,
            methods=["GET"],
        )

        # ── 第三方登录 ──────────────────────────────────────────────
        # 已集成的 OAuth2 登录方式，供前端渲染登录入口
        bp.add_url_rule(
            "/oauth/providers",
            view_func=self.oauth_handler.get_oauth_providers,
            methods=["GET"],
        )
        # 指定提供商的授权页地址，前端拿到后跳转用户即可
        bp.add_url_rule(
            "/oauth/<string:provider_name>/authorize",
            view_func=self.oauth_handler.get_oauth_authorize,
            methods=["GET"],
        )
        # 第三方授权回调：平台带 code 跳回这里，换取登录凭证
        bp.add_url_rule(
            "/oauth/<string:provider_name>",
            view_func=self.oauth_handler.oauth_login,
            methods=["GET"],
        )

        app.register_blueprint(bp)


__all__ = ["Router"]
