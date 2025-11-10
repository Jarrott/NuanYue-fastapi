"""
☁️ WalletSyncService
负责同步余额至 RTDB + Redis（被 BaseWalletSyncService 调用）
"""

import time
from app.extension.google_tools.firebase_admin_service import rtdb
from app.extension.redis.redis_client import rds


class WalletSyncService:
    BASE_PATH = "wallet_sync"

    @staticmethod
    async def sync_balance(user_id: int, balance_usd: float):
        """
        🔄 同步用户余额到 Firebase RTDB + Redis
        """
        try:
            # ✅ Firebase RTDB
            ref = rtdb.reference(f"user_{user_id}")
            ref.update({
                "balance": str(round(balance_usd, 2)),
                "currency": "USD",
                "last_update": int(time.time())
            })
            print(f"[RTDB] ✅ 更新成功 user_{user_id} = {balance_usd}")
        except Exception as e:
            print(f"[WARN] RTDB 更新失败: {e}")

        try:
            # ✅ Redis 缓存
            redis = await rds.instance()
            await redis.hset(f"user:{user_id}:wallet", mapping={
                "balance": str(balance_usd),
                "currency": "USD",
                "updated_at": int(time.time())
            })
            print(f"[Redis] ✅ 更新成功 user:{user_id}:wallet = {balance_usd}")
        except Exception as e:
            print(f"[WARN] Redis 更新失败: {e}")
