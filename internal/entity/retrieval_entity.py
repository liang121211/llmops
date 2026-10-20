"""检索召回相关的实体常量。"""


class RetrievalStrategy:
    """检索策略：向量检索、全文检索、混合检索。"""

    VECTOR = "vector"
    FULL_TEXT = "full_text"
    HYBRID = "hybrid"


# 允许的检索策略集合，用于请求参数校验
RETRIEVAL_STRATEGIES = (
    RetrievalStrategy.VECTOR,
    RetrievalStrategy.FULL_TEXT,
    RetrievalStrategy.HYBRID,
)


class QuerySource:
    """知识库查询记录的来源。"""

    # 召回检索测试（hit-testing 接口）
    RECALL_TEST = "recall_test"
    # App 调用
    APP = "app"
    # Debugger 调试
    DEBUGGER = "debugger"


# 混合检索默认权重：全文 : 向量 = 0.5 : 0.5
DEFAULT_HYBRID_WEIGHT = 0.5
# 最大召回数量默认值
DEFAULT_TOP_K = 3
# 最小匹配度默认值（0 表示不过滤）
DEFAULT_SCORE_THRESHOLD = 0.0
# 检索记录列表默认返回条数
DEFAULT_QUERY_RECORD_LIMIT = 10


__all__ = [
    "RetrievalStrategy",
    "RETRIEVAL_STRATEGIES",
    "QuerySource",
    "DEFAULT_HYBRID_WEIGHT",
    "DEFAULT_TOP_K",
    "DEFAULT_SCORE_THRESHOLD",
    "DEFAULT_QUERY_RECORD_LIMIT",
]
