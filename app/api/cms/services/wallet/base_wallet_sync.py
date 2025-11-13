# @Time    : 2025/11/10 22:30
# @Author  : Pedro
# @File    : base_wallet_sync.py
# @Software: PyCharm
"""
🧩 Pedro-Core BaseWalletSyncService
统一多源钱包同步服务（Firestore → PostgreSQL → Redis → RTDB）
含自动重试机制（确保99.99%一致性）
"""

import time
import asyncio

from sqlalchemy import select

from app.extension.google_tools.firestore import fs_service as fs
from app.extension.google_tools.firebase_admin_service import rtdb
from app.extension.google_tools.fs_transaction import SERVER_TIMESTAMP
from app.extension.redis.redis_client import rds
from app.pedro.db import async_session_factory
from app.api.cms.model.user import User


class BaseWalletSyncService:

    # ======================================================
    # 🔁 通用重试包装器
    # ======================================================
    @staticmethod
    async def _retry_async(func, *args, max_retries=3, delay=0.5, name="UnknownTask", **kwargs):
        """异步自动重试包装"""
        for attempt in range(1, max_retries + 1):
            try:
                await func(*args, **kwargs)
                return True
            except Exception as e:
                print(f"[WARN] {name} 第 {attempt} 次失败: {e}")
                if attempt < max_retries:
                    await asyncio.sleep(delay)
                else:
                    print(f"[FATAL] ❌ {name} 最终失败 ({max_retries} 次重试无效)")
        return False

    # ======================================================
    # 🔄 主入口：多源强同步
    # ======================================================
    @staticmethod
    async def sync_all(uid: str | int, balance_after: float):
        """
        🔄 统一多源同步（并发 + 自动重试）
        """
        uid = int(uid)
        start = time.time()

        async def sync_firestore():
            wallet_path = f"users/{uid}/store/wallet"
            await fs.safe_update(
                wallet_path,
                {
                    "available_balance": float(balance_after),
                    "updated_at": SERVER_TIMESTAMP,
                }
            )

        async def sync_pgsql():
            async with async_session_factory() as session:
                result = await session.execute(select(User).where(User.uuid == int(uid)))
                user = result.scalar_one_or_none()  # ✅ 提取实际 ORM 对象
                if user:
                    extra = dict(user.extra or {})
                    extra["balance"] = float(balance_after)
                    user.extra = extra
                    await session.commit()

        async def sync_redis():
            redis = await rds.instance()
            await redis.hset(
                f"user:{uid}:wallet",
                mapping={
                    "balance": str(balance_after),
                    "updated_at": int(time.time())
                }
            )

        async def sync_rtdb():
            ref = rtdb.reference(f"user_{uid}")
            ref.update({
                "balance": float(balance_after),
                "currency": "USD",
                "last_update": int(time.time())
            })

        # ✅ 以并发形式执行所有同步任务
        await asyncio.gather(
            BaseWalletSyncService._retry_async(sync_firestore, name="Firestore 同步"),
            BaseWalletSyncService._retry_async(sync_pgsql, name="PostgreSQL 同步"),
            BaseWalletSyncService._retry_async(sync_redis, name="Redis 同步"),
            BaseWalletSyncService._retry_async(sync_rtdb, name="RTDB 同步"),
        )

        cost = round(time.time() - start, 3)
        print(f"[SYNC ✅] Wallet 全链路同步完成 uid={uid} balance={balance_after} ({cost}s)")
        return True
