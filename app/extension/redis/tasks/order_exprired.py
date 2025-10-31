"""
# @Time    : 2025/10/31 23:06
# @Author  : Pedro
# @File    : order_exprired.py
# @Software: PyCharm
"""
from app.extension.websocket.wss import websocket_manager

async def handle_order_expired(redis_svc, order_id: str):
    # 这里写业务逻辑，比如后台设置订单完成时间后，到期自动完成，写入金额等
    print(f"⏳ TTL订单过期处理完成：{order_id}")
