import hashlib
import hmac


def hash_password(password, salt):
    """使用 HMAC-SHA256 生成密码摘要。"""
    return hmac.new(salt.encode("utf-8"), password.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_password(password, salt, password_hash):
    """校验明文密码是否匹配摘要。"""
    return hmac.compare_digest(hash_password(password, salt), password_hash)


__all__ = ["hash_password", "verify_password"]
