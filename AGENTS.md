# AGENTS.md

## 项目概览

这是一个基于 Python 的智能体管理平台。

## 技术栈

- 框架：Flask + Postgres + Langchain + LangGraph
- 语言：Python
- 测试：PyTest

## 开发命令

使用 PyCharm IDE 进行开发时，由 Agent 自行运行相关执行命令，包含：

- 编译
- 运行
- 测试

## 代码规范

- 文件名：全部小写字母，使用下划线分隔单词，例如 `app_service.py`。尽可能保证文件作用单一，不要把所有代码写在同一个文件中。
- 类名：驼峰命名法，以大写字母开头，例如 `class AppService`。多个单词之间不使用下划线。
- 函数名和方法：小写字母，下划线分隔，例如 `get_account`、`generate_token`。
- 变量名：小写字母，下划线分隔，例如 `my_variable`、`token_count`。
- 常量：全大写字母，下划线分隔，例如 `MAX_SIZE`、`PI`。
- 私有变量与方法：以下划线开头，例如 `_my_private_variable`、`_my_private_method()`。这是约定而非强制；外部代码不应调用私有成员。
- 模块名：与文件名类似，全部小写并用下划线分隔。目录作为包时创建 `__init__.py`，并尽可能用 `__all__` 导出。

## 项目结构

```
项目根目录
├── app                  # app 目录
│   └── http             # 程序的主入口文件
├── config               # 配置目录
├── docker               # docker 包
├── Dockerfile           # docker 构建文件
├── Dockerfile-unstructured
├── docs                 # 项目说明文档
├── internal             # 内部核心包
│   ├── core             # 核心层包
│   ├── entity           # 实体常量包
│   ├── exception        # 异常包
│   ├── extension        # 扩展包
│   ├── handler          # 控制层包
│   ├── lib              # 常用的库包
│   ├── middleware       # 中间件包
│   ├── migration        # 数据库迁移目录（目录不是包）
│   ├── model            # ORM 模型包
│   ├── router           # 路由包
│   ├── schedule         # 调度包
│   ├── schema           # 请求响应协议规范包
│   ├── server           # HTTP 服务包
│   ├── service          # 服务层包
│   └── task             # 异步任务包
├── pkg                  # 常见功能包
│   ├── oauth            # 认证包
│   ├── paginator        # 分页包
│   ├── password         # 密码模块
│   ├── response         # 给用户请求响应的模块包
│   └── sqlalchemy       # 数据库连接包
├── pytest.ini
├── README.md
├── requirements.txt
├── storage
│   └── vector_store     # 向量存储目录
└── test                 # 测试包
```

## 架构约束

- 注入使用 `inject`
- 所有配置存放到 `.env`
- 数据库连接使用 Flask-SQLAlchemy
- HTTP 请求校验使用 flask-form 表单校验
- HTTP 返回数据拼装使用 marshmallow
- AI 业务使用 LangChain / LangGraph
- 文档存储使用腾讯云 OSS，现阶段用本地 MinIO，后期切换腾讯云
- 文档加载使用 unstructured
- 向量数据库使用本地 Weaviate
- `app` / `handler` / `service` / `core` 代码能注入则尽量注入
- 方法需添加适当注释（不强制文档字符串）；核心业务逻辑必须写注释
- 前期未接入 logging，允许用 `print` 临时替代
- 所有前端请求的 API 必须添加 pytest 测试

## 流程约束

用户请求的数据处理流程：

`post/get --> router --> handler --> 数据校验（flask-form） --> service -->（如有 AI 业务）core --> 数据拼装（marshmallow） --> 返回给用户`
