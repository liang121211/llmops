class AppService:
    """应用服务层。"""

    def ping(self):
        # 健康检查不走 AI 核心，直接返回心跳数据
        return {"message": "pong"}


__all__ = ["AppService"]
