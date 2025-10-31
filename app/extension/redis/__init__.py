"""
# @Time    : 2025/10/26 20:43
# @Author  : Pedro
# @File    : __init__.py.py
# @Software: PyCharm
"""
from .tasks.order_exprired import handle_order_expired

TTL_HANDLERS = {
    "order:": handle_order_expired,
}


async def dispatch_ttl_event(redis_svc, expired_key: str):
    try:
        for prefix, handler in TTL_HANDLERS.items():
            if expired_key.startswith(prefix):
                item_id = expired_key.split(prefix, 1)[-1]
                return await handler(redis_svc, item_id)
    except Exception as e:
        raise e

    print(f"⚠️ Redis TTL 未匹配 key={expired_key}")
