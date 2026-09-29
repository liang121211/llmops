import traceback

from flask import Flask

from config import Config
from internal.exception import CustomException
from internal.pkg.response import HttpCode, Response, json
from internal.router.router import Router


class Http(Flask):
    """继承 Flask 的 HTTP 服务，启动时完成配置加载与路由注册。"""

    def __init__(self, router: Router, config: Config):
        super().__init__(__name__)
        # 将配置对象载入 Flask 配置
        self.config.from_object(config)
        self.register_error_handler(Exception, self._register_error_handler)
        router.register_router(self)

    def _register_error_handler(self, error: Exception):
        if isinstance(error, CustomException):
            traceback.print_exception(type(error), error, error.__traceback__)
            return json(
                Response(
                    code=error.code,
                    message=error.message,
                    data=error.data,
                )
            )
        if self.debug:
            raise error
        return json(
            Response(
                code=HttpCode.FAIL,
                message=str(error),
                data={},
            )
        )


__all__ = ["Http"]
