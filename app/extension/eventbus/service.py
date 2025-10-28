# app/extension/eventbus/service.py
import asyncio
from app.extension.eventbus.base import eventbus
from app.extension.eventbus.adapter_redis import RedisAdapter
from app.extension.eventbus.adapter_ws import WebSocketAdapter
from app.extension.eventbus.adapter_mq import MQAdapter
from app.pedro.service_manager import BaseService  # ✅ 继承你的基类


class EventBusService(BaseService):
    """统一事件总线服务"""
    name = "eventbus"

    def __init__(self):
        self.redis_adapter = RedisAdapter()
        self.ws_adapter = WebSocketAdapter()
        self.mq_adapter = MQAdapter()
        self.tasks = []

    async def init(self):
        """初始化 EventBus"""
        await self.redis_adapter.init()
        await self.mq_adapter.init()

        # 注册适配器
        eventbus.register_adapter(self.redis_adapter)
        eventbus.register_adapter(self.ws_adapter)
        eventbus.register_adapter(self.mq_adapter)

        # 启动 Redis 监听任务
        self.tasks.append(asyncio.create_task(
            self.redis_adapter.subscribe(self._on_event_received)
        ))

        print("🚀 EventBusService 已启动")

    async def _on_event_received(self, payload):
        """收到 Redis 广播后重新分发"""
        event_name = payload.get("event")
        data = payload.get("data", {})
        await eventbus.publish(event_name, data)

    async def close(self):
        for t in self.tasks:
            t.cancel()
        print("🧹 EventBusService 已关闭")
