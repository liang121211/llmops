from abc import ABC, abstractmethod


class BaseAgent(ABC):
    """所有智能体的通用父类。"""

    @abstractmethod
    def run(
        self,
        query: str,
        history: list | None = None,
        long_term_memory: str = "",
    ) -> str:
        """执行一次智能体调用。

        参数依次是查询、短期记忆（历史消息）、长期记忆（历史摘要），
        返回最终答案；执行过程的事件通过队列管理器发布。
        """


__all__ = ["BaseAgent"]
