# app/extension/rabbitmq/services.py
from aio_pika import ExchangeType
from app.extension.rabbitmq.constances import (
    EXCHANGE_DELAY, QUEUE_ORDER_DELAY, ROUTING_ORDER_DELAY
)
from app.extension.rabbitmq.rabbit import rabbit
from app.extension.rabbitmq.tasks import dispatch_task
from app.pedro.service_manager import BaseService



class RabbitService(BaseService):
    name = "rabbitmq"

    def __init__(self):
        self._initialized = False

    async def init(self):
        """初始化 RabbitMQ 延迟队列"""
        if self._initialized:
            print("⚠️ RabbitService 已初始化，跳过重复注册")
            return

        channel = await rabbit._ensure_channel()
        await channel.set_qos(prefetch_count=10)

        # 1️⃣ 声明延迟交换机（插件已启用）
        args = {"x-delayed-type": "direct"}
        exchange = await channel.declare_exchange(
            EXCHANGE_DELAY,
            ExchangeType.X_DELAYED_MESSAGE,
            durable=True,
            arguments=args,
        )

        # 2️⃣ 声明队列 + 绑定（这一步是关键）
        queue = await channel.declare_queue(
            QUEUE_ORDER_DELAY,
            durable=True
        )
        await queue.bind(exchange, routing_key=ROUTING_ORDER_DELAY)

        print(f"✅ RabbitService: 已声明并绑定 {QUEUE_ORDER_DELAY} → {EXCHANGE_DELAY}")

        # 3️⃣ 启动消费者
        async def callback(msg):
            async with msg.process():
                import json
                data = json.loads(msg.body.decode())
                await dispatch_task(data)
        await queue.consume(callback)
        print(f"✅ RabbitService: 已开始消费 {QUEUE_ORDER_DELAY}")

    async def close(self):
        await rabbit.close()
        print("🛑 RabbitService 已关闭")
