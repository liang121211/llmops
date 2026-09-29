from math import ceil


def build_paginator(total, current_page, page_size):
    """根据总数生成分页元数据。"""
    page_size = max(int(page_size), 1)
    current_page = max(int(current_page), 1)
    total_page = ceil(total / page_size) if total else 0
    return {
        "total": total,
        "current_page": current_page,
        "page_size": page_size,
        "total_page": total_page,
    }


__all__ = ["build_paginator"]
