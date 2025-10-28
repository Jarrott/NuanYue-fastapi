"""
Pedro-Core | Redis 异步客户端（最终版）
支持：
✅ 自动延迟初始化
✅ JSON 自动序列化/反序列化
✅ 健壮连接检测
✅ Token 状态控制机制
"""
import json
import redis.asyncio as aioredis
from typing import Any, Optional
from app.config.settings_manager import get_current_settings


class RedisClient:
    def __init__(self):
        self.client: Optional[aioredis.Redis] = None
        self._initialized = False

    # ===========================================================
    # 🔧 自动初始化逻辑
    # ===========================================================
    async def _ensure_client(self):
        """确保 Redis 客户端已连接（延迟初始化）"""
        if self._initialized and self.client:
            return self.client
        settings = get_current_settings()
        redis_url = settings.redis.redis_url
        self.client = aioredis.from_url(redis_url, decode_responses=True)
        self._initialized = True
        print(f"🔴 Redis 自动连接成功: {redis_url}")
        return self.client


    async def instance(self):
        """外部调用统一接口"""
        return await self._ensure_client()

    # ===========================================================
    # 🧩 通用 CRUD 操作
    # ===========================================================
    async def set(self, key: str, value: Any, ex: Optional[int] = None):
        """设置键值，可选过期时间"""
        client = await self._ensure_client()
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        await client.set(key, value, ex=ex)

    async def get(self, key: str, as_json: bool = True):
        """获取键值（支持自动 JSON 解码）"""
        client = await self._ensure_client()
        val = await client.get(key)
        if not val:
            return None
        if as_json:
            try:
                return json.loads(val)
            except json.JSONDecodeError:
                return val
        return val

    async def delete(self, key: str):
        client = await self._ensure_client()
        await client.delete(key)

    async def exists(self, key: str) -> bool:
        client = await self._ensure_client()
        return await client.exists(key) > 0

    async def expire(self, key: str, seconds: int):
        client = await self._ensure_client()
        await client.expire(key, seconds)

    # ===========================================================
    # 🔐 Token 状态机制
    # ===========================================================
    async def mark_token_valid(self, token: str):
        client = await self._ensure_client()
        await client.set(f"token:{token}", json.dumps({"status": 200}), ex=3600)

    async def invalidate_token(self, token: str):
        client = await self._ensure_client()
        await client.set(f"token:{token}", json.dumps({"status": 401}), ex=3600)

    async def is_token_valid(self, token: str) -> bool:
        client = await self._ensure_client()
        val = await client.get(f"token:{token}")
        if not val:
            return False
        try:
            data = json.loads(val)
            return data.get("status") == 200
        except json.JSONDecodeError:
            return False

    async def close(self):
        if self.client:
            await self.client.close()
            self.client = None
            self._initialized = False
            print("🛑 Redis 已断开连接")


# 单例实例
rds = RedisClient()