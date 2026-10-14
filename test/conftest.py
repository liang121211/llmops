import json
import os

os.environ.setdefault("SECRET_KEY", "test-secret-key")

import pytest
from sqlalchemy import delete, select

from app.http.app import app
from internal.model import ApiTool, ApiToolProvider, Dataset, Document, ProcessRule, UploadFile
from internal.pkg.response import HttpCode
from pkg.sqlalchemy import db

# 预置的分页测试数据：数量与前缀固定，便于重复执行时识别同名数据
API_TOOL_SEED_TOTAL = 25
API_TOOL_SEED_PREFIX = "分页测试插件"
API_TOOL_SEED_URL = "/api-tools"
# TODO: 等待授权认证模块完成后再进行切换调整
API_TOOL_SEED_ACCOUNT_ID = "a666a888-8888-6666-1234-b9d69212aaaa"


def api_tool_seed_payload(index: int) -> dict:
    """构造一条创建请求，名字固定，规范里带一个工具和两个参数。"""
    schema = {
        "description": f"分页测试插件 {index:02d} 提供的字典查询能力",
        "server": "https://dict.youdao.com",
        "paths": {
            "/suggest": {
                "get": {
                    "description": "根据传递的单词查询其字典信息",
                    "operationId": f"SeedSuggest{index:02d}",
                    "parameters": [
                        {
                            "name": "q",
                            "in": "query",
                            "description": "要检索查询的单词，例如love/computer",
                            "required": True,
                            "type": "str",
                        },
                        {
                            "name": "doctype",
                            "in": "query",
                            "description": "返回的数据类型，支持json和xml两种格式",
                            "required": False,
                            "type": "str",
                        },
                    ],
                }
            }
        },
    }
    return {
        "name": f"{API_TOOL_SEED_PREFIX}{index:02d}",
        "icon": f"https://example.com/static/api-tool/seed-{index:02d}.png",
        "openapi_schema": json.dumps(schema, ensure_ascii=False),
        "headers": [{"key": "Authorization", "value": f"Bearer seed-token-{index:02d}"}],
    }


@pytest.fixture(scope="session", autouse=True)
def api_tool_seed():
    """用 POST /api-tools 预置分页测试数据。

    数据只增不删，重复执行时同名提供商会被跳过，因此可以反复跑。
    """
    created = 0
    skipped = 0
    names = []
    # debug 模式下全局异常处理会 re-raise，导致已存在时 test_client 抛异常而非返回 JSON
    original_debug = app.debug
    app.debug = False
    try:
        with app.test_client() as client:
            for index in range(1, API_TOOL_SEED_TOTAL + 1):
                payload = api_tool_seed_payload(index)
                names.append(payload["name"])
                body = client.post(API_TOOL_SEED_URL, json=payload).get_json()
                if body["code"] == HttpCode.SUCCESS.value:
                    created += 1
                elif body["message"] == f"API工具提供者 {payload['name']} 已经存在":
                    # 上一次执行已经创建过，直接复用
                    skipped += 1
                else:
                    pytest.fail(f"预置分页测试数据失败：{body}")
    finally:
        app.debug = original_debug
    print(f"分页测试数据准备完成：新增 {created} 条，复用 {skipped} 条")
    return {
        "total": API_TOOL_SEED_TOTAL,
        "created": created,
        "skipped": skipped,
        "names": names,
    }


@pytest.fixture
def client():
    app.config.update(TESTING=True)
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture
def app_context():
    with app.app_context():
        yield


def account_provider_ids() -> set:
    """当前账号下已有的提供商 id，用来识别用例自己新建的数据。"""
    stmt = select(ApiToolProvider.id).where(
        ApiToolProvider.account_id == API_TOOL_SEED_ACCOUNT_ID
    )
    return set(db.session.execute(stmt).scalars().all())


@pytest.fixture
def clean_api_tools(app_context):
    """用例真实写库，结束后只清理用例新建的行，保留预置的分页测试数据。"""
    before = account_provider_ids()
    yield
    created = [
        provider_id
        for provider_id in account_provider_ids()
        if provider_id not in before
    ]
    if not created:
        return
    with db.auto_commit():
        db.session.execute(delete(ApiTool).where(ApiTool.provider_id.in_(created)))
        db.session.execute(
            delete(ApiToolProvider).where(ApiToolProvider.id.in_(created))
        )


def account_upload_file_ids() -> set:
    """当前账号下已有的上传文件 id，用来识别用例自己新建的数据。"""
    stmt = select(UploadFile.id).where(
        UploadFile.account_id == API_TOOL_SEED_ACCOUNT_ID
    )
    return set(db.session.execute(stmt).scalars().all())


@pytest.fixture
def clean_upload_files(app_context):
    """上传用例真实写库，结束后只清理用例新建的文件记录。"""
    before = account_upload_file_ids()
    yield
    created = [
        upload_file_id
        for upload_file_id in account_upload_file_ids()
        if upload_file_id not in before
    ]
    if not created:
        return
    with db.auto_commit():
        db.session.execute(delete(UploadFile).where(UploadFile.id.in_(created)))


def account_dataset_ids() -> set:
    """当前账号下已有的知识库 id，用来识别用例自己新建的数据。"""
    stmt = select(Dataset.id).where(
        Dataset.account_id == API_TOOL_SEED_ACCOUNT_ID
    )
    return set(db.session.execute(stmt).scalars().all())


@pytest.fixture
def clean_datasets(app_context):
    """知识库用例真实写库，结束后只清理用例新建的记录。"""
    before = account_dataset_ids()
    yield
    created = [
        dataset_id
        for dataset_id in account_dataset_ids()
        if dataset_id not in before
    ]
    if not created:
        return
    from internal.model.app_dataset_join import AppDatasetJoin

    with db.auto_commit():
        db.session.execute(
            delete(AppDatasetJoin).where(AppDatasetJoin.dataset_id.in_(created))
        )
        db.session.execute(delete(Document).where(Document.dataset_id.in_(created)))
        db.session.execute(
            delete(ProcessRule).where(ProcessRule.dataset_id.in_(created))
        )
        db.session.execute(delete(Dataset).where(Dataset.id.in_(created)))
