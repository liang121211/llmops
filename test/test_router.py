import inject
import pytest
from flask import Flask

import app.http.app  # noqa: F401  导入即完成 inject 容器配置
from internal.router.router import Router


@pytest.fixture
def router():
    return inject.instance(Router)


def test_register_router_creates_blueprint(router):
    app = Flask("router_test")

    router.register_router(app)

    assert "app" in app.blueprints


def test_register_router_registers_expected_rules(router):
    app = Flask("router_test")

    router.register_router(app)

    rules = {
        str(rule): rule
        for rule in app.url_map.iter_rules()
        if rule.endpoint != "static"
    }

    BUILTIN_TOOL_RULE = (
        "/builtin-tools/<string:provider_name>/tools/<string:tool_name>"
    )
    BUILTIN_ICON_RULE = "/builtin-tools/<string:provider_name>/icon"
    VALIDATE_SCHEMA_RULE = "/api-tools/validate-openapi-schema"
    API_TOOLS_RULE = "/api-tools"
    API_TOOL_PROVIDER_RULE = "/api-tools/<uuid:provider_id>"
    API_TOOL_DETAIL_RULE = "/api-tools/<uuid:provider_id>/tools/<string:tool_name>"
    API_TOOL_INVOKE_RULE = "/api-tools/invoke/<uuid:provider_id>/<string:tool_name>"
    UPLOAD_FILE_RULE = "/upload-files/file"
    UPLOAD_IMAGE_RULE = "/upload-files/image"
    DOCUMENT_LOAD_RULE = "/document/<uuid:upload_file_id>/load"
    CELERY_DEMO_TASK_RULE = "/celery/demo_task"
    DATASETS_RULE = "/datasets"
    DATASET_DETAIL_RULE = "/datasets/<uuid:dataset_id>"
    DATASET_DOCUMENTS_RULE = "/datasets/<uuid:dataset_id>/documents"
    assert set(rules) == {
        "/ping",
        "/app/chat",
        "/app/builtin_tool_test",
        "/app",
        "/builtin-tools",
        "/builtin-tools/categories",
        BUILTIN_ICON_RULE,
        BUILTIN_TOOL_RULE,
        VALIDATE_SCHEMA_RULE,
        API_TOOLS_RULE,
        API_TOOL_PROVIDER_RULE,
        API_TOOL_DETAIL_RULE,
        API_TOOL_INVOKE_RULE,
        UPLOAD_FILE_RULE,
        UPLOAD_IMAGE_RULE,
        DOCUMENT_LOAD_RULE,
        CELERY_DEMO_TASK_RULE,
        DATASETS_RULE,
        DATASET_DETAIL_RULE,
        DATASET_DOCUMENTS_RULE,
    }
    assert "GET" in rules["/ping"].methods
    assert "POST" in rules["/app/chat"].methods
    assert "GET" not in rules["/app/chat"].methods
    # 内置插件测试接口只开放 POST
    assert "POST" in rules["/app/builtin_tool_test"].methods
    assert "GET" not in rules["/app/builtin_tool_test"].methods
    # /app 上挂着四条规则，用请求方法区分增删改查
    app_methods = set()
    for rule in app.url_map.iter_rules():
        if str(rule) == "/app":
            app_methods |= rule.methods - {"OPTIONS", "HEAD"}
    assert app_methods == {"POST", "GET", "PUT", "DELETE"}
    # 内置插件查询接口只开放 GET
    assert "GET" in rules["/builtin-tools"].methods
    assert "POST" not in rules["/builtin-tools"].methods
    assert "GET" in rules[BUILTIN_TOOL_RULE].methods
    # 分类列表与提供商图标同样只开放 GET
    assert "GET" in rules["/builtin-tools/categories"].methods
    assert "POST" not in rules["/builtin-tools/categories"].methods
    assert "GET" in rules[BUILTIN_ICON_RULE].methods
    # 静态的分类路径独立成规则，不会被动态段抢走
    assert rules["/builtin-tools/categories"].arguments == set()
    assert rules[BUILTIN_ICON_RULE].arguments == {"provider_name"}
    # openapi 规范校验接口只开放 POST
    assert "POST" in rules[VALIDATE_SCHEMA_RULE].methods
    assert "GET" not in rules[VALIDATE_SCHEMA_RULE].methods
    assert rules[VALIDATE_SCHEMA_RULE].arguments == set()
    # 创建自定义 API 工具只开放 POST，分页列表只开放 GET，两者共用 /api-tools
    api_tools_methods = set()
    for rule in app.url_map.iter_rules():
        if str(rule) == API_TOOLS_RULE:
            api_tools_methods |= rule.methods - {"OPTIONS", "HEAD"}
    assert api_tools_methods == {"POST", "GET"}
    assert rules[API_TOOLS_RULE].arguments == set()
    # 提供商详情与删除共用 /api-tools/<provider_id>，用请求方法区分
    provider_methods = set()
    for rule in app.url_map.iter_rules():
        if str(rule) == API_TOOL_PROVIDER_RULE:
            provider_methods |= rule.methods - {"OPTIONS", "HEAD"}
    assert provider_methods == {"GET", "DELETE"}
    assert rules[API_TOOL_PROVIDER_RULE].arguments == {"provider_id"}
    # 工具详情只开放 GET，且需要提供商与工具名两个动态段
    assert "GET" in rules[API_TOOL_DETAIL_RULE].methods
    assert "DELETE" not in rules[API_TOOL_DETAIL_RULE].methods
    assert rules[API_TOOL_DETAIL_RULE].arguments == {"provider_id", "tool_name"}
    # 调用工具只开放 POST，静态的 invoke 段不会被 uuid 转换器抢走
    assert "POST" in rules[API_TOOL_INVOKE_RULE].methods
    assert "GET" not in rules[API_TOOL_INVOKE_RULE].methods
    assert rules[API_TOOL_INVOKE_RULE].arguments == {"provider_id", "tool_name"}
    # 文件上传与图片上传都只开放 POST，且没有动态段
    for upload_rule in (UPLOAD_FILE_RULE, UPLOAD_IMAGE_RULE):
        assert "POST" in rules[upload_rule].methods
        assert "GET" not in rules[upload_rule].methods
        assert rules[upload_rule].arguments == set()
    # 文档加载只开放 GET，需要 upload_file_id 动态段
    assert "GET" in rules[DOCUMENT_LOAD_RULE].methods
    assert "POST" not in rules[DOCUMENT_LOAD_RULE].methods
    assert rules[DOCUMENT_LOAD_RULE].arguments == {"upload_file_id"}
    # celery demo 任务：POST 提交、GET 查询，共用同一路径
    celery_methods = set()
    for rule in app.url_map.iter_rules():
        if str(rule) == CELERY_DEMO_TASK_RULE:
            celery_methods |= rule.methods - {"OPTIONS", "HEAD"}
    assert celery_methods == {"POST", "GET"}
    assert rules[CELERY_DEMO_TASK_RULE].arguments == set()
    # 知识库：POST 创建、GET 列表，共用 /datasets
    datasets_methods = set()
    for rule in app.url_map.iter_rules():
        if str(rule) == DATASETS_RULE:
            datasets_methods |= rule.methods - {"OPTIONS", "HEAD"}
    assert datasets_methods == {"POST", "GET"}
    assert rules[DATASETS_RULE].arguments == set()
    # 知识库详情/修改/删除共用 /datasets/<dataset_id>
    dataset_detail_methods = set()
    for rule in app.url_map.iter_rules():
        if str(rule) == DATASET_DETAIL_RULE:
            dataset_detail_methods |= rule.methods - {"OPTIONS", "HEAD"}
    assert dataset_detail_methods == {"GET", "PUT", "DELETE"}
    assert rules[DATASET_DETAIL_RULE].arguments == {"dataset_id"}
    # 知识库文档创建只开放 POST
    assert "POST" in rules[DATASET_DOCUMENTS_RULE].methods
    assert "GET" not in rules[DATASET_DOCUMENTS_RULE].methods
    assert rules[DATASET_DOCUMENTS_RULE].arguments == {"dataset_id"}


def test_registered_view_functions_are_handler_methods(router):
    app = Flask("router_test")

    router.register_router(app)

    handler = router.app_handler
    assert app.view_functions["app.ping"] == handler.ping
    assert app.view_functions["app.chat"] == handler.chat
    assert app.view_functions["app.builtin_tool_test"] == handler.builtin_tool_test
    assert app.view_functions["app.create_app"] == handler.create_app
    assert app.view_functions["app.get_apps"] == handler.get_apps
    assert app.view_functions["app.update_app"] == handler.update_app
    assert app.view_functions["app.delete_app"] == handler.delete_app
    builtin_handler = router.builtin_handler
    assert (
        app.view_functions["app.get_builtin_tools"] == builtin_handler.get_builtin_tools
    )
    assert (
        app.view_functions["app.get_provider_tool"] == builtin_handler.get_provider_tool
    )
    assert (
        app.view_functions["app.get_categories"] == builtin_handler.get_categories
    )
    assert (
        app.view_functions["app.get_provider_icon"]
        == builtin_handler.get_provider_icon
    )
    assert (
        app.view_functions["app.validate_openapi_schema"]
        == router.api_tool_handler.validate_openapi_schema
    )
    assert (
        app.view_functions["app.create_openapi_schema"]
        == router.api_tool_handler.create_openapi_schema
    )
    assert (
        app.view_functions["app.get_providers_with_page"]
        == router.api_tool_handler.get_providers_with_page
    )
    assert (
        app.view_functions["app.get_provider"] == router.api_tool_handler.get_provider
    )
    assert (
        app.view_functions["app.delete_provider"]
        == router.api_tool_handler.delete_provider
    )
    assert app.view_functions["app.get_tool"] == router.api_tool_handler.get_tool
    assert (
        app.view_functions["app.invoke_tool"] == router.api_tool_handler.invoke_tool
    )
    assert (
        app.view_functions["app.upload_file"]
        == router.upload_file_handler.upload_file
    )
    assert (
        app.view_functions["app.upload_image"]
        == router.upload_file_handler.upload_image
    )
    assert (
        app.view_functions["app.create_demo_task"]
        == router.celery_handler.create_demo_task
    )
    assert (
        app.view_functions["app.get_demo_task"]
        == router.celery_handler.get_demo_task
    )
    assert (
        app.view_functions["app.create_dataset"]
        == router.dataset_handler.create_dataset
    )
    assert (
        app.view_functions["app.get_datasets"]
        == router.dataset_handler.get_datasets
    )
    assert (
        app.view_functions["app.get_dataset"]
        == router.dataset_handler.get_dataset
    )
    assert (
        app.view_functions["app.update_dataset"]
        == router.dataset_handler.update_dataset
    )
    assert (
        app.view_functions["app.delete_dataset"]
        == router.dataset_handler.delete_dataset
    )
    assert (
        app.view_functions["app.create_documents"]
        == router.dataset_handler.create_documents
    )
    assert (
        app.view_functions["app.load_document"]
        == router.document_handler.load_document
    )


def test_ping_view_returns_pong(router):
    app = Flask("router_test")

    router.register_router(app)

    assert app.view_functions["app.ping"]() == {"ping": "pong"}
