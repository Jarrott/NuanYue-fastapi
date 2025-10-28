"""
Pedro-Core | RabbitMQ 异步客户端（支持自动延迟连接）
"""
import json
import aio_pika
from aio_pika import Message
from typing import Any, Optional, Callable
from app.config.settings_manager import get_current_settings


class RabbitClient:
    def __init__(self):
        self._connection = None
        self._channel = None
        self._initialized = False

    async def _ensure_channel(self):
        """确保连接和通道存在"""
        if self._initialized and self._channel:
            return self._channel
        settings = get_current_settings()
        url = settings.rabbitmq.amqp_url
        self._connection = await aio_pika.connect_robust(url)
        self._channel = await self._connection.channel()
        self._initialized = True
        print(f"🐇 RabbitMQ 已连接: {url}")
        return self._channel

    async def publish(self, body: Any, routing_key: str, exchange_name: str = ""):
        """发送消息（自动连接）"""
        channel = await self._ensure_channel()
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        msg = Message(body)
        await channel.default_exchange.publish(msg, routing_key=routing_key)
        print(f"📤 发布消息到 {routing_key}: {body}")

    async def consume(self, queue_name: str, callback: Callable[[Any], Any]):
        """消费消息"""
        channel = await self._ensure_channel()
        queue = await channel.declare_queue(queue_name, durable=True)
        await queue.consume(lambda msg: self._process(msg, callback))
        print(f"✅ 已开始监听队列 {queue_name}")

    @staticmethod
    async def _process(msg, callback):
        async with msg.process():
            data = msg.body.decode()
            try:
                data = json.loads(data)
            except Exception:
                pass
            await callback(data)

    async def close(self):
        """关闭连接"""
        if self._connection:
            await self._connection.close()
            self._initialized = False
            print("🛑 RabbitMQ 已断开连接")


# ✅ 单例实例
rabbit = RabbitClient()