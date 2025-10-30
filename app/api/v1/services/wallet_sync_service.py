from app.extension.google_tools.rtdb import FirebaseRTDB
from app.extension.redis.redis_client import rds
import time


class WalletSyncService:
    BASE = "wallet_sync"

    @staticmethod
    async def sync_balance(user_id: int, usdt: float):
        # ✅ 更新 Firebase
        rtdb = FirebaseRTDB(WalletSyncService.BASE)
        rtdb.update(f"user_{user_id}", {
            "USDT": str(usdt),
            "last_update": int(time.time())
        })
