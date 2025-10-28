import aio_pika
import asyncio
import json
import uuid
from app.config.settings_manager import get_current_settings

class MQAdapter:
    """MQ 广播适配器（含防回环机制）"""
    SOURCE_ID = str(uuid.uuid4())

    def __init__(self):
        settings = get_current_settings()
        self.url = settings.rabbitmq.amqp_url
        self.conn = None
        self.channel = None
        self.exchange = None
        self.queue = None
        self._connected = False

    async def init(self):
        self.conn = await aio_pika.connect_robust(self.url)
        self.channel = await self.conn.channel()
        self.exchange = await self.channel.declare_exchange(
            "eventbus", aio_pika.ExchangeType.FANOUT, durable=True
        )
        self.queue = await self.channel.declare_queue(exclusive=True)
        await self.queue.bind(self.exchange)
        self._connected = True
        print(f"✅ MQAdapter 已连接 {self.url}")

    async def publish(self, event_name: str, payload: dict):
        """带源标识的广播"""
        if not self._connected:
            await self.init()
        payload["_src"] = MQAdapter.SOURCE_ID
        await self.exchange.publish(
            aio_pika.Message(
                body=json.dumps(payload).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            ),
            routing_key=""
        )

    async def subscribe(self, callback):
        if not self._connected:
            await self.init()

        async with self.queue.iterator() as it:
            async for msg in it:
                async with msg.process():
                    data = json.loads(msg.body.decode())
                    if data.get("_src") == MQAdapter.SOURCE_ID:
                        continue  # 🚫 忽略自己发出的广播
                    await callback(data)

    async def close(self):
        if self.conn and not self.conn.is_closed:
            await self.conn.close()
        self._connected = False
        print("🛑 MQAdapter 已关闭")
