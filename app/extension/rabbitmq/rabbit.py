import json
from datetime import timedelta

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
        """发布延迟消息 (支持 '15m' / '2h' / timedelta / 秒整数)"""

        # ------ ✅ 转换 delay 表达方式为毫秒 ------
        def _to_ms(val):
            # timedelta
            if isinstance(val, timedelta):
                return int(val.total_seconds() * 1000)

            # 数字 → 默认按秒处理 (避免老代码误传秒数导致秒变毫秒)
            if isinstance(val, (int, float)):
                # 如果传入大于一天的值，我们认为用户已经传 ms
                return val if val > 86400 else int(val * 1000)

            # 字符串：支持 s/m/h/d
            if isinstance(val, str):
                v = val.strip().lower()
                unit = v[-1]
                num = float(v[:-1])

                mapping = {
                    "s": num * 1000,
                    "m": num * 60 * 1000,
                    "h": num * 60 * 60 * 1000,
                    "d": num * 24 * 60 * 60 * 1000,
                }
                if unit in mapping:
                    return int(mapping[unit])

                raise ValueError(f"❌ 不支持的 delay 格式: {val}")

            raise TypeError("delay_ms 必须是 int/float/timedelta/字符串(如 '15m')")

        delay_ms = _to_ms(delay_ms)
        # -------------------------------------------

        ch = await self._ensure_channel()
        exchange = await ch.get_exchange(EXCHANGE_DELAY)
        msg = aio_pika.Message(
            body=json.dumps(message).encode(),
            headers={"x-delay": delay_ms},
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            content_type="application/json",
        )
        await exchange.publish(msg, routing_key=ROUTING_ORDER_DELAY)

        print(
            f"📦 [PublishDelay] {EXCHANGE_DELAY}:{ROUTING_ORDER_DELAY} "
            f"delay={delay_ms}ms body={message}"
        )

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

    def _to_delay_ms(self, delay):
        # timedelta 支持
        if isinstance(delay, timedelta):
            return int(delay.total_seconds() * 1000)

        # int 秒 支持
        if isinstance(delay, (int, float)):
            return int(delay * 1000)

        # 字符串格式支持 ("15m" "2h" "1d")
        if isinstance(delay, str):
            delay = delay.strip().lower()
            unit = delay[-1]
            value = int(delay[:-1])

            if unit == "s":  # 秒
                return value * 1000
            if unit == "m":  # 分
                return value * 60 * 1000
            if unit == "h":  # 小时
                return value * 60 * 60 * 1000
            if unit == "d":  # 天
                return value * 24 * 60 * 60 * 1000

            raise ValueError(f"不支持的时间格式: {delay}")

        raise TypeError("delay 必须是 timedelta / int 秒 / '15m'-风格字符串")

# ✅ 单例
rabbit = RabbitClient()
