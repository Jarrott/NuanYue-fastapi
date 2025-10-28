# app/extension/eventbus/service.py
import asyncio
import uuid
from app.extension.eventbus.base import eventbus
from app.extension.eventbus.adapter_redis import RedisAdapter
from app.extension.eventbus.adapter_ws import WebSocketAdapter
from app.extension.eventbus.adapter_mq import MQAdapter
from app.pedro.service_manager import BaseService


class EventBusService(BaseService):
    """统一事件总线服务"""
    name = "eventbus"

    def __init__(self):
        self.redis_adapter = RedisAdapter()
        self.ws_adapter = WebSocketAdapter()
        self.mq_adapter = MQAdapter()
        self.tasks: list[asyncio.Task] = []
        self._initialized = False
        self._source_id = str(uuid.uuid4())  # ✅ 本节点唯一 ID，防回环

    async def init(self):
        """初始化 EventBus（只执行一次）"""
        if self._initialized:
            print("⚠️ EventBusService 已初始化，跳过重复注册")
            return
        self._initialized = True

        # 1️⃣ 初始化所有适配器
        await asyncio.gather(
            self.redis_adapter.init(),
            self.mq_adapter.init()
        )
        await self.ws_adapter.init()  # WSAdapter 一般为同步类，也保持一致性

        # 2️⃣ 注册适配器（幂等）
        eventbus.register_adapter(self.redis_adapter)
        eventbus.register_adapter(self.ws_adapter)
        eventbus.register_adapter(self.mq_adapter)

        # 3️⃣ 启动监听任务
        self.tasks.append(asyncio.create_task(
            self.redis_adapter.subscribe(self._on_external_event)
        ))
        self.tasks.append(asyncio.create_task(
            self.mq_adapter.subscribe(self._on_external_event)
        ))

        print("🚀 EventBusService 启动完成：Redis + MQ + WS 已注册")

    async def _on_external_event(self, payload: dict):
        """当收到 MQ/Redis 广播时，分发到本地 EventBus（带源标识过滤）"""
        src = payload.get("_src")
        event = payload.get("event")
        data = payload.get("data", {})

        # 忽略自己发布的消息
        if src == self._source_id:
            return

        # 增加源标识，防止再次广播回去
        data["_src"] = self._source_id
        await eventbus.publish(event, data)

    async def close(self):
        """优雅关闭所有任务和连接"""
        for t in self.tasks:
            t.cancel()
        await asyncio.gather(
            self.redis_adapter.close(),
            self.mq_adapter.close(),
            return_exceptions=True
        )
        print("🧹 EventBusService 已关闭")
