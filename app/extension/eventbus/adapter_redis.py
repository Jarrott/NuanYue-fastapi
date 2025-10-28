import json
import asyncio
import redis.asyncio as aioredis
from app.config.settings_manager import get_current_settings

class RedisAdapter:
    def __init__(self):
        self.client = None
        self.pubsub = None

    async def init(self):
        settings = get_current_settings()
        self.client = aioredis.from_url(settings.redis.redis_url, decode_responses=True)
        self.pubsub = self.client.pubsub()
        await self.pubsub.subscribe("eventbus")
        print("🔴 RedisAdapter 订阅 eventbus 成功")

    async def publish(self, event_name, payload):
        if self.client:
            await self.client.publish("eventbus", json.dumps(payload))

    async def subscribe(self, callback):
        """后台任务，持续接收 Redis 广播"""
        async for message in self.pubsub.listen():
            if message["type"] == "message":
                try:
                    payload = json.loads(message["data"])
                    await callback(payload)
                except Exception as e:
                    print(f"⚠️ RedisAdapter 解析错误: {e}")
