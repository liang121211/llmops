from datetime import datetime, timezone


def utc_now():
    """返回当前 UTC 时间。"""
    return datetime.now(timezone.utc)


__all__ = ["utc_now"]
