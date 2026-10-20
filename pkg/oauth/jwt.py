import datetime
import uuid

import jwt


def generate_token(
    account_id,
    secret_key: str,
    expire_days: int = 30,
    algorithm: str = "HS256",
) -> str:
    """签发用户 JWT 凭证，默认 30 天过期。"""
    issued_at = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "iat": issued_at,
        "exp": issued_at + datetime.timedelta(days=expire_days),
        # jti 让同一账号两次登录得到的凭证互不相同
        "jti": uuid.uuid4().hex,
        "data": {"account_id": str(account_id)},
    }
    return jwt.encode(payload, secret_key, algorithm=algorithm)


def parse_token(token: str, secret_key: str, algorithm: str = "HS256") -> dict:
    """解析并校验 JWT，签名不匹配或已过期时抛出 jwt.InvalidTokenError。"""
    return jwt.decode(token, secret_key, algorithms=[algorithm])


def get_account_id_from_token(
    token: str, secret_key: str, algorithm: str = "HS256"
) -> str | None:
    """从 JWT 取出账号 id，凭证无效时返回 None，供请求加载器使用。"""
    try:
        payload = parse_token(token, secret_key, algorithm)
    except jwt.InvalidTokenError:
        return None
    data = payload.get("data") or {}
    return data.get("account_id")


__all__ = ["generate_token", "get_account_id_from_token", "parse_token"]
