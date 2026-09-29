class OAuthClient:
    """OAuth 客户端占位，后续接入具体提供商。"""

    def get_authorize_url(self, redirect_uri):
        return redirect_uri


__all__ = ["OAuthClient"]
