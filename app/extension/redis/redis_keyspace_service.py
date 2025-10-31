# app/extension/redis_keyspace_service.py
import asyncio
from urllib.parse import urlparse

from app.pedro.service_manager import BaseService, ServiceManager
from app.pedro.config import get_current_settings
from . import dispatch_ttl_event


class RedisKeyspaceService(BaseService):
    name = "redis_keyspace"

    async def init(self):
        self.redis_svc = ServiceManager.get("redis")
        await self.redis_svc._ensure_client()
        self.redis = self.redis_svc.client

        s = get_current_settings()
        parsed = urlparse(s.redis.redis_url)
        self.db_index = int(parsed.path.replace("/", "") or 0)
        self.channel = f"__keyevent@{self.db_index}__:expired"

        # 异步启动监听任务
        self._task = asyncio.create_task(self._listen())

        print(f"📡 Redis Keyspace Listener Ready: {self.channel}")

    async def _listen(self):
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(self.channel)

        async for msg in pubsub.listen():
            if msg.get("type") != "message":
                continue

            expired_key = msg.get("data")
            if isinstance(expired_key, bytes):
                expired_key = expired_key.decode()

            print(f"📥 TTL Key Detected: {expired_key}")

            # ✅ 统一交给路由器调度
            await dispatch_ttl_event(self.redis_svc, expired_key)

    async def close(self):
        if hasattr(self, "_task"):
            self._task.cancel()
        print("🛑 RedisKeyspaceService closed")
