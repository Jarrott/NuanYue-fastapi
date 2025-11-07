"""
# @Time    : 2025/11/8 2:00
# @Author  : Pedro
# @File    : wallet_sync_service.py
# @Software: PyCharm
"""
import time
import asyncio
from app.extension.google_tools.rtdb import FirebaseRTDB
from app.extension.redis.redis_client import rds


class WalletSyncService:
    BASE_PATH = "wallet_sync"

    @staticmethod
    async def sync_balance(user_id: int, balance_usd: float):
        """
        🔄 同步用户余额到 Firebase RTDB + Redis
        """
        try:
            # ✅ Firebase Realtime Database 更新
            rtdb = FirebaseRTDB(WalletSyncService.BASE_PATH)
            rtdb.update(f"user_{user_id}", {
                "balance": str(round(balance_usd, 2)),
                "currency": "USD",
                "last_update": int(time.time())
            })

            # ✅ Redis 缓存更新
            redis = await rds.instance()
            await redis.hset(f"user:{user_id}:wallet", mapping={
                "balance": str(balance_usd),
                "currency": "USD",
                "updated_at": int(time.time())
            })

        except Exception as e:
            print(f"⚠️ WalletSyncService 同步失败: {e}")
