from dataclasses import dataclass

import inject
from flask import request

from internal.pkg.response import success_json, validate_error_json
from internal.schema.oauth_schema import (
    OAuthCallbackReq,
    OAuthLoginSchema,
    OAuthProviderSchema,
)
from internal.service.oauth_service import OAuthService


@inject.autoparams()
@dataclass
class OAuthHandler:
    """第三方登录控制层：提供商列表、授权地址、授权回调登录。"""

    oauth_service: OAuthService

    def get_oauth_providers(self):
        """获取平台已集成的第三方授权登录方式。"""
        providers = self.oauth_service.get_providers()
        return success_json(
            {"providers": OAuthProviderSchema(many=True).dump(providers)}
        )

    def get_oauth_authorize(self, provider_name: str):
        """取指定提供商的授权页地址，前端把用户跳过去即可开始登录。"""
        authorize_url = self.oauth_service.get_authorize_url(provider_name)
        return success_json({"provider": provider_name, "authorize_url": authorize_url})

    def oauth_login(self, provider_name: str):
        """第三方带 code 回调：完成授权登录并返回平台 JWT 与帐号信息。"""
        # 1. flask-form 校验回调里的授权码
        form = OAuthCallbackReq(formdata=request.args)
        if not form.validate():
            return validate_error_json(form.errors)
        # 2. 服务层换令牌、取用户信息、建号或复用并签发 JWT
        result = self.oauth_service.login(
            provider_name=provider_name,
            code=form.code.data,
            ip=request.remote_addr or "",
        )
        # 3. marshmallow 拼装响应，has_password 决定前端是否展示初始化密码入口
        return success_json(OAuthLoginSchema().dump(result))


__all__ = ["OAuthHandler"]
