from config.default_config import DEFAULT_CONFIG


class Config:
    """Flask 应用配置对象，实例属性即为 Flask 配置项。"""

    def __init__(self):
        # 载入默认配置项目
        for key, value in DEFAULT_CONFIG.items():
            setattr(self, key, value)
        # 写死关闭 WTF 表单的 CSRF 校验
        self.WTF_CSRF_ENABLED = False


__all__ = ["Config"]
