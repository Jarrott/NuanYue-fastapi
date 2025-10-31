"""
# @Time    : 2025/10/31 20:08
# @Author  : Pedro
# @File    : __init__.py.py
# @Software: PyCharm
"""
from .order_task import handle_order_timeout
from .vip_task import handle_vip_expire
from .cart_task import handle_cart_expire

TASK_HANDLERS = {
    "order_expire": handle_order_timeout,
    "vip_expire": handle_vip_expire,
    "cart_expire": handle_cart_expire,
    # 待加入新的任务
}

async def dispatch_task(data: dict):
    task_type = data.get("task_type")
    handler = TASK_HANDLERS.get(task_type)

    if not handler:
        return print(f"⚠️ 未知任务类型: {task_type}")

    await handler(data)
