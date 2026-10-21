# LLMOPS11 API

## 架构

参考图

### 项目依赖

```text
pip install flask inject flask-cors flask-wtf python-dotenv pytest marshmallow flask-sqlalchemy flask-migrate psycopg2
pip install langchain langchain-community langchain-openai langchain-huggingface
# pip install cos-python-sdk-v5 # for Tencent COS
pip install minio
pip install redis celery eventlet # optional: celery-types
pip install flask-weaviate langchain-weaviate
pip install sentence-transformers
pip install jieba # optional: simsimd
pip install flask-login pyjwt

##########
python-docx docx2txt unstructured
pdfminer.six==20221105
unstructured==0.10.30
pi_heif unstructured_inference pdf2image
```

## 依赖注入

依赖注入（Dependency Injection，简称 DI）是一种设计模式，用于将对象的依赖关系从内部管理转移到外部管理。
这样可以提高代码的可测试性、可维护性和可扩展性。

不需要手动创建对象， `injector` 会自动处理：

1. 创建对象
2. 对象内部的依赖对象，也会创建，解决依赖问题

使用方式，需要进行依赖注入的类上添加装饰器： `@inject` ，会被自动管理，自动解决依赖创建对象，如何获取： `injector.get(类)`

## 项目创建

提示词：默认情况下，使用 `AGENTS.MD` 文件作为 AI 每次都会读取的上下文文件。

```text
# AGENTS.md
## 项目概览

这是一个基于Python的智能体管理平台

## 技术栈

- 框架：Flask + Postgres + Langchain + LangGraph
- 语言：Python
- 测试：PyTest

## 开发命令

使用的是 PyCharm IDE 进行开发请你自己运行相关执行命令，包含：

- 编译
- 运行
- 测试

## 代码规范

- 文件名 
使用全部小写字母。 
使用下划线分隔单词，例如： app_service.py 。 
尽可能保证文件作用的单一，不要把所有代码一次性写在同一个文件中。 
- 类名 
使用驼峰命名法，例如：class AppService.
类名应该以大写字母开头，每个单词的首字母都大写。 
如果类名由多个单词组成，单词之间不使用下划线分割。 
-  函数名和方法 
使用小写字母。使用下划线分隔单词。 例如： get_account ， generate_token 等。3.4 变量名 使用小写字母。使用下划线分隔单词。 例如： my_variable ， token_count 。 
- 常量 
使用全大写字母。 使用下划线分隔单词。 例如： MAX_SIZE ， PI 等。 
- 私有变量与方法 
以一个下划线开头表示私有，例如： _my_private_variable ， _my_private_method() 等。 在 Python 中并没有严格的私有变量/方法，这种命名约定只是一种约定，而不是强制规则，实际上这些变量/方法仍然可以被使用，但是作为一种约定，在外部调用时，不应该调用私有的变量与方法。 
- 模块名 
与文件名类似，使用全部小写字母，使用下划线分隔单词。 例如： my_module.py 对应的模块名应该是 my_module 。 模块下创建 __init__.py 文件代表当前目录为一个模块，并尽可能在 __init__.py 中使用__all__ 简导出  

## 项目结构

项目根目录
├── app  # app 目录
│   └── http # 程序的主入口文件
├── config  # 配置目录
├── docker  # docker包
├── Dockerfile # docker构建文件
├── Dockerfile-unstructured # docker构建文件
├── docs  # 项目说明文档
├── internal # 内部核心包
│    ├── core # 核心层包
│    ├── entity # 实体常量包
│    ├── exception # 异常包
│    ├── extension # 扩展包
│    ├── handler # 控制层包
│    ├── lib # 常用的库包
│    ├── middleware # 中间件包
│    ├── migration  # 数据库迁移目录(这是目录不是包)
│    ├── model # Orm模型包
│    ├── router # 路由包
│    ├── schedule # 调度包
│    ├── schema   # 请求响应的协议 规范 包
│    ├── server  # 服务 http 服务包
│    ├── service # 服务层包
│    └── task # 任务 异步任务包
├── pkg # 常见的功能包包
│    ├── oauth   # 认证包
│    ├── paginator # 分页包
│    ├── password # 密码模块
│    ├── response # 响应 给用户请求响应的模块包
│    └── sqlalchemy # 数据库链接包
├── pytest.ini # 测试pytest初始化文件
├── README.md  # 文档
├── requirements.txt # 依赖
├── storage  # 向量存目录
│     └── vector_store
└── test # 测试包

## 架构约束

- 注入使用的是 inject
- 所有的配置都存放到 .env 文件里
- 数据库连接使用的 flask-SQLAlchemy
- http 的数据请求校验使用的 flask-form 表单校验
- http 返回的数据拼装使用的 marshmallow
- AI 业务使用的框架使用的是 langchain langGraph
- 文档存储使用的是腾讯云的 oss，暂时使用本地部署的 minIO ，后期再使用腾讯云
- 文档加载使用的 unstructured 包
- 向量数据库使用的是本地部署的 weaviate
- 所有 app/handler/service/core 代码能够使用注入尽量使用注入
- 编写的方法都需要添加适当的注释，不要求文档注释，设计核心业务逻辑的代码都应该添加注释
- 项目开发初期没有使用 logging 日志，后期整合了日志模块后再添加相关日志，前期允许使用 print 临时替代
- 测试非常重要，所有的前端请求的 API 必须添加 pytest 测试

## 流程约束

用户请求的数据处理流程是：
`post/get--->router--->handler---->数据校验（flask-form）--->service--(如果有AI业务)--->core-----数据拼装（marshmallow）--->返回给用户`

```

## 第一个API接口

提示词：

```text
请你按照如下步骤帮我创建代码,请你遵循 @AGENTS.md规范
- 在 internal/server 目录下新建一个 http.py 文件,创建一个Http类集成Flask，传入的参数有Router类
- 在 internal/router 目录下新建一个 router.py 文件,创建一个Router类使用 inject 注解和 dataclass 注解，并实现 register_router 函数参数是Flask，这函数的目前要实现的功能是:
  1、创建一个蓝图
  2、将这个蓝图注册到 Flask App 中
- 在 internal/handler 下面新建一个 app_handler.py 实现一个AppHandler类,使用inject注解，和dataclass注解，并实现一个ping 成员函数，该函数固定返回 {"ping":"pong"}，并在 __init__.py 中导出这个类
- 在 router.py 中注入 AppHandler 类，并且在蓝图中添加 ping 函数作为视图函数，方法是 get
- 在 app.py 中实例化 Http 类，其中 Router 类来从 inject 的容器中获取(这个容器请你在app.py中实例化)
- 在 app.py 请你初始化环境变量 dotenv
```

```text
## docker-compse容器编排
### redis 编排需求:
1、镜像使用:redis:6-alpine
2、总是重启
3、容器名:llmops-redis
4、卷映射: ./volumes/redis:/data 
5、启动时候需要密码，llmops123456
6、健康检查 
7、需要端口映射外网访问 

### postgres编排需求:
1、镜像使用:postgres:15-alpine 
2、总是重启
3、配置环境变量 用户是 postgres ， 密码是 llmops123456   数据路径 /var/lib/postgresql/data/pgdata
4、卷标映射:将本地路径 ./volumes/db/data 映射到上面的数据路径 
5、将本地初始化脚本   ./postgres/init.sql映射到/docker-entrypoint-initdb.d/init.sql路径 
6、健康检查，每3秒一次，超时3s  重试 30次
7、需要端口映射外网访问 

### weaviate容器编排需求
1、镜像使用:semitechnologies/weaviate:1.28.4
2、容器名:llmops-weaviate
3、总是重启
4、配置环境变量 
- 查询默认返回数据条数是 25 
- 需要授权才能和weaviate 进行交互 
- 数据存储路径是  /var/lib/weaviate 
- 不需要向量化模块 
- 节点的主机名字是'node1'
- 启用基于API密钥的身份验证 
- 允许的api密钥列表是 'ftBC9hKkjfdbdi0wW3T6kEtMh5BZFpGa1DF8'
- 允许api密钥访问的用户列表是:'llmops@alltman.com'
- 启动管理员列表授权 
- 由管理员权限的 用户列表是:'llmops@alltman.com'
5、卷标映射:将本地路径 ./volumes/weaviate 映射到上面的数据路径
6、需要端口映射外网访问（http 和 grpc 都要） 

### api容器编排需求 
1、镜像使用:llmops-api:0.9.9.9
2、容器名:llmops-api， 本地构建，构建路径是 ../ui, 编译文件是DockerFile 
3、容器名称:llmops-api 
4、总是重启
5、配置环境变量留空 
6、卷标映射，./volumes/app/storage:/app/api/storage
7、端口:5001 且外网能访问 
8、启动依赖: llmops-db  llmops-redis  llmops-weaviate
```
