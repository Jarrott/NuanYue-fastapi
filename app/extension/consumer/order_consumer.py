"""
# @Time    : 2025/10/28 22:14
# @Author  : Pedro
# @File    : order_consumer.py
# @Software: PyCharm
"""
import asyncio
from app.pedro.service_manager import ServiceManager
from app.extension.websocket.wss import websocket_manager

class OrderConsumer:
    async def start(self):
        rabbit = ServiceManager.get("rabbitmq")
        redis = ServiceManager.get("redis")
        channel = rabbit.channel
        queue = await channel.get_queue("order_dead")

        async with queue.iterator() as q:
            async for msg in q:
                async with msg.process():
                    order_id = msg.body.decode()
                    print(f"🕓 [Consumer] 收到过期订单: {order_id}")

                    # 更新redis状态
                    await redis.record_event(order_id, "expired")

                    # 通知用户（假设订单中存了user_id）
                    user_id = order_id.split(":")[0]  # 示例
                    await websocket_manager.send_to_user(user_id, {
                        "type": "order_expired",
                        "order_id": order_id,
                        "msg": "订单已过期"
                    })
