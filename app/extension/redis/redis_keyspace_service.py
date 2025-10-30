# app/extension/redis_keyspace_service.py
import asyncio
import json
from app.extension.service_manager import BaseService, ServiceManager
from app.extension.websocket.wss import websocket_manager
from app.pedro.config import get_current_settings

class RedisKeyspaceService(BaseService):
    name = "redis_keyspace"

    async def init(self):
        # 依赖 RedisService
        self.redis_svc = ServiceManager.get("redis")  # 确保 redis services 先加载
        self.redis = self.redis_svc.redis

        s = get_current_settings()
        self.db_index = s.redis_db
        self.channel = f"__keyevent@{self.db_index}__:expired"

        self._task = asyncio.create_task(self._listen())
        print(f"📡 RedisKeyspaceService 订阅: {self.channel}")

    async def _listen(self):
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(self.channel)
        async for msg in pubsub.listen():
            if msg.get("type") != "message":
                continue
            expired_key = msg.get("data")  # e.g. "order:pending:{order_id}"
            if isinstance(expired_key, bytes):
                expired_key = expired_key.decode()

            if not expired_key.startswith("order:pending:"):
                continue

            order_id = expired_key.split("order:pending:", 1)[-1]
            await self._handle_order_pending_expired(order_id)

    async def _handle_order_pending_expired(self, order_id: str):
        """pending哨兵过期 → 判断订单是否已完成；未完成则置为过期并推送"""
        status_key = f"order:status:{order_id}"
        data_key = f"order:data:{order_id}"

        status = await self.redis_svc.get(status_key)
        if status == "completed":
            # 已完成，无需处理（可能在TTL内完成）
            return

        # 置为过期
        await self.redis_svc.set(status_key, "expired")
        info = await self.redis_svc.hgetall(data_key)  # 包含 uid, item_id 等
        uid = info.get("uid") or "unknown"

        payload = {
            "type": "order_expired",
            "order_id": order_id,
            "msg": "订单已过期",
        }
        await websocket_manager.send_to_user(uid, payload)
        print(f"⏳ 订单过期处理完成：{order_id} → 推送给 uid={uid}")

    async def close(self):
        if hasattr(self, "_task"):
            self._task.cancel()
        print("🛑 RedisKeyspaceService closed")
