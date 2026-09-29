from flask import jsonify

from pkg.response.http_code import FAIL, SUCCESS


def success_json(data=None, message="success"):
    """拼装成功响应。"""
    return jsonify({"code": SUCCESS, "message": message, "data": data})


def fail_json(message="fail", data=None):
    """拼装失败响应。"""
    return jsonify({"code": FAIL, "message": message, "data": data})


__all__ = ["success_json", "fail_json"]
