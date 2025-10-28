"""
# @Time    : 2025/10/28 21:49
# @Author  : Pedro
# @File    : order_worker.py
# @Software: PyCharm
"""
import asyncio
import json
import aio_pika
import redis as aioredis
from app.extension.websocket.wss import websocket_manager
from app.pedro.config import get_current_settings

settings = get_current_settings()
REDIS_URL = settings.redis.redis_url
RABBITMQ_URL = settings.rabbitmq.rabbitmq_url


async def process_order(msg: aio_pika.IncomingMessage):
    async with msg.process():
        payload = json.loads(msg.body)
        order_id = payload["order_id"]
        uid = payload["uid"]

        redis = await aioredis.from_url(REDIS_URL)
        await redis.set(f"order:{order_id}:status", "completed", ex=3600)

        await websocket_manager.send_to_user(uid, f"🎉 您的订单 {order_id} 已完成 ✅")
        print(f"✅ 已完成订单 {order_id} 并推送给 {uid}")

async def consume_orders():
    conn = await aio_pika.connect_robust(RABBITMQ_URL)
    channel = await conn.channel()
    queue = await channel.declare_queue("order.delay", durable=True)
    await queue.consume(process_order)
    print("📡 已启动订单延迟队列消费者 ...")

    while True:
        await asyncio.sleep(5)
