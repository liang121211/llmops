from flask_wtf import FlaskForm
from marshmallow import Schema, fields
from wtforms import StringField
from wtforms.validators import DataRequired, Length


class OAuthCallbackReq(FlaskForm):
    """第三方授权回调校验：Gitee 等平台带 code 跳回 redirect_uri。"""

    code = StringField(
        "code",
        validators=[
            DataRequired(message="code参数必须传递"),
            Length(max=512, message="code参数最大长度为512字符"),
        ],
    )


class OAuthProviderSchema(Schema):
    """可用的第三方登录方式，前端用来渲染登录入口。"""

    name = fields.String()
    label = fields.String()
    description = fields.String()


class OAuthAccountSchema(Schema):
    """登录后返回的帐号信息。"""

    id = fields.UUID()
    name = fields.String()
    email = fields.String()


class OAuthLoginSchema(Schema):
    """第三方登录结果：has_password 为假时前端需要给出初始化密码入口。"""

    token = fields.String()
    oauth_access_token = fields.String()
    is_new_account = fields.Boolean()
    has_password = fields.Boolean()
    account = fields.Nested(OAuthAccountSchema)


__all__ = [
    "OAuthAccountSchema",
    "OAuthCallbackReq",
    "OAuthLoginSchema",
    "OAuthProviderSchema",
]
