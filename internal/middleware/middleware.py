def register_middleware(app):
    """注册 HTTP 中间件。"""

    @app.after_request
    def _after_request(response):
        return response


__all__ = ["register_middleware"]
