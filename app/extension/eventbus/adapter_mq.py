"""
# @Time    : 2025/10/28 21:56
# @Author  : Pedro
# @File    : adapter_mq.py
# @Software: PyCharm
"""
# app/extension/eventbus/adapter_mq.py
import aio_pika
import asyncio
import json
from app.config.settings_manager import get_current_settings


class MQAdapter:
    """EventBus 的 MQ 适配器，用于多实例间广播事件"""
    def __init__(self):
        settings = get_current_settings()
        self.url = settings.rabbitmq.url  # ✅ 从配置文件读取
        self.conn: aio_pika.RobustConnection | None = None
        self.channel: aio_pika.Channel | None = None
        self.exchange: aio_pika.Exchange | None = None
        self.queue: aio_pika.Queue | None = None
        self._connected = False

    # ===========================================================
    # 🔧 初始化连接
    # ===========================================================
    async def init(self):
        """初始化 MQ 连接并声明事件交换机"""
        try:
            self.conn = await aio_pika.connect_robust(self.url)
            self.channel = await self.conn.channel()
            self.exchange = await self.channel.declare_exchange(
                "eventbus", aio_pika.ExchangeType.FANOUT, durable=True
            )
            self.queue = await self.channel.declare_queue(exclusive=True)
            await self.queue.bind(self.exchange)

            self._connected = True
            print(f"✅ MQAdapter 已连接: {self.url}")
        except Exception as e:
            print(f"❌ MQAdapter 初始化失败: {e}")
            self._connected = False

    # ===========================================================
    # 📡 发布事件
    # ===========================================================
    async def publish(self, event_name: str, payload: dict):
        """发布事件到 MQ（广播给所有实例）"""
        if not self._connected:
            await self.init()

        try:
            await self.exchange.publish(
                aio_pika.Message(
                    body=json.dumps(payload).encode("utf-8"),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key=""
            )
        except Exception as e:
            print(f"⚠️ MQAdapter.publish 出错: {e}")
            # 自动重连再试
            await asyncio.sleep(1)
            await self.init()

    # ===========================================================
    # 🔔 订阅事件
    # ===========================================================
    async def subscribe(self, callback):
        """持续监听 MQ 广播并分发到 EventBus"""
        if not self._connected:
            await self.init()

        async with self.queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    try:
                        data = json.loads(message.body.decode("utf-8"))
                        await callback(data)
                    except Exception as e:
                        print(f"⚠️ MQAdapter 消息解析异常: {e}")

    # ===========================================================
    # 🧹 清理资源
    # ===========================================================
    async def close(self):
        if self.channel and not self.channel.is_closed:
            await self.channel.close()
        if self.conn and not self.conn.is_closed:
            await self.conn.close()
        self._connected = False
        print("🛑 MQAdapter 已关闭")
