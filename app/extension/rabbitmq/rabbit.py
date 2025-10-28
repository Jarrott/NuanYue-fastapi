import json
import aio_pika
from aio_pika import Message
from typing import Any, Callable
from app.config.settings_manager import get_current_settings
from app.extension.rabbitmq.constances import ROUTING_ORDER_DELAY, EXCHANGE_DELAY


class RabbitClient:
    def __init__(self):
        self._connection = None
        self._channel = None
        self._initialized = False

    async def _ensure_channel(self):
        """确保通道存在"""
        if self._initialized and self._channel:
            return self._channel

        settings = get_current_settings()
        url = settings.rabbitmq.url
        self._connection = await aio_pika.connect_robust(url)
        self._channel = await self._connection.channel()
        self._initialized = True
        print(f"🐇 RabbitMQ 已连接: {url}")
        return self._channel

    # async def publish_delay(self, queue: str, message: Any, delay_ms: int = 10000):
    #     """
    #     发布延迟消息（基于 x-delayed-message 插件）
    #     """
    #     channel = await self._ensure_channel()
    #     if isinstance(message, (dict, list)):
    #         message = json.dumps(message, ensure_ascii=False)
    #     if isinstance(message, str):
    #         message = message.encode()
    #
    #     args = {"x-delayed-type": "direct"}
    #     exchange = await channel.declare_exchange(
    #         "delay-exchange",
    #         aio_pika.ExchangeType.X_DELAYED_MESSAGE,
    #         durable=False,
    #         arguments=args,
    #     )
    #
    #     queue_obj = await channel.declare_queue(queue, durable=True)
    #     await queue_obj.bind(exchange, routing_key=queue)
    #
    #     await exchange.publish(
    #         aio_pika.Message(
    #             body=message,
    #             headers={"x-delay": delay_ms},
    #             delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
    #         ),
    #         routing_key=queue,
    #     )
    #     print(f"📦 已发布延迟消息 -> {queue} | 延迟 {delay_ms / 1000:.1f}s")
    async def publish_delay(self, message: dict, delay_ms: int = 10_000):
        ch = await self._ensure_channel()
        exchange = await ch.get_exchange(EXCHANGE_DELAY)
        msg = aio_pika.Message(
            body=json.dumps(message).encode(),
            headers={"x-delay": delay_ms},
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            content_type="application/json",
        )
        await exchange.publish(msg, routing_key=ROUTING_ORDER_DELAY)
        print(f"📦 [PublishDelay] -> {EXCHANGE_DELAY}:{ROUTING_ORDER_DELAY} "
              f"delay={delay_ms}ms body={message}")


    async def consume(self, queue_name: str, callback: Callable[[Any], Any]):
        """消费消息"""
        channel = await self._ensure_channel()
        queue = await channel.declare_queue(queue_name, durable=True)
        await queue.consume(lambda msg: self._process(msg, callback))
        print(f"✅ 已开始监听队列 {queue_name}")

    @staticmethod
    async def _process(msg, callback):
        async with msg.process():
            body = msg.body.decode()
            try:
                data = json.loads(body)
            except Exception:
                data = body
            await callback(data)

    async def close(self):
        if self._connection:
            await self._connection.close()
            self._initialized = False
            print("🛑 RabbitMQ 已关闭连接")

# ✅ 单例
rabbit = RabbitClient()
