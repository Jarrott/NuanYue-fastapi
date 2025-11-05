# app/extension/eventbus/services.py
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
        self._source_id = str(uuid.uuid4())

    async def init(self):
        if self._initialized:
            print("⚠️ EventBusService 已初始化，跳过重复注册")
            return
        self._initialized = True

        # ✅ Init adapters
        await asyncio.gather(
            self.redis_adapter.init(),
            self.mq_adapter.init()
        )
        await self.ws_adapter.init()

        # ✅ Register adapters (idempotent)
        eventbus.register_adapter(self.redis_adapter)
        eventbus.register_adapter(self.ws_adapter)
        eventbus.register_adapter(self.mq_adapter)

        # ✅ Start background listeners (non-blocking)
        self.tasks.append(asyncio.create_task(self._safe_subscribe(self.redis_adapter)))
        self.tasks.append(asyncio.create_task(self._safe_subscribe(self.mq_adapter)))

        print("🚀 EventBusService 启动完成：Redis + MQ + WS 已注册")

    async def _safe_subscribe(self, adapter):
        """后台订阅任务，稳定版"""
        await asyncio.sleep(1)  # ⏳ Give services time to boot (fix startup crash)

        while True:
            try:
                await adapter.subscribe(self._on_external_event)
            except asyncio.CancelledError:
                print(f"🛑 {adapter.__class__.__name__} 订阅任务取消")
                break
            except Exception as e:
                print(f"⚠️ {adapter.__class__.__name__} subscribe error: {e}, retrying...")
                await asyncio.sleep(2)

    async def _on_external_event(self, payload: dict):
        src = payload.get("_src")
        event = payload.get("event")
        data = payload.get("data", {})

        if src == self._source_id:
            return

        data["_src"] = self._source_id
        await eventbus.publish(event, data)

    async def close(self):
        for t in self.tasks:
            t.cancel()

        await asyncio.gather(
            self.redis_adapter.close(),
            self.mq_adapter.close(),
            return_exceptions=True
        )
        print("🧹 EventBusService 已关闭")
