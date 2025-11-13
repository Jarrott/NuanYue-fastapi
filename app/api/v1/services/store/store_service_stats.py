# -*- coding: utf-8 -*-
"""
# @Time    : 2025/11/13 22:45
# @Author  : Pedro
# @File    : store_service_stats.py
# @Software: PyCharm
"""
from app.extension.google_tools.firestore import fs_service
from app.extension.google_tools.fs_transaction import SERVER_TIMESTAMP, Increment
from app.pedro.db import async_session_factory
from app.api.v1.model.shop_product import ShopProduct


class StoreServiceStats():
    """
    🧩 Pedro-Core StoreService 扩展版（兼容继承）
    ------------------------------------------------
    ✅ 不影响原 StoreService 调用
    ✅ 新增自动初始化与统计同步功能
    ✅ 支持收藏、访问量、信用分等实时更新
    """

    # ======================================================
    # 🧮 初始化店铺统计信息
    # ======================================================
    @staticmethod
    async def init_stats(uid: str):
        """若不存在统计信息，则自动初始化"""
        path = f"users/{uid}/store/meta/stats"
        doc = await fs_service.get(path)
        if doc:
            print(f"ℹ️ stats 已存在: {uid}")
            return

        default_data = {
            "product_count": 0,
            "followers": 0,
            "visits": 0,
            "rating": 5.0,
            "credit_score": 100,
            "deposit": 0.0,
            "create_time": SERVER_TIMESTAMP,
            "update_time": SERVER_TIMESTAMP,
        }
        await fs_service.set(path, default_data)
        print(f"✅ 初始化店铺统计信息成功: {uid}")

    # ======================================================
    # ✅ 同步商品数量
    # ======================================================
    @staticmethod
    async def sync_product_count(uid: str):
        async with async_session_factory() as session:
            result = await session.execute(ShopProduct.count_by_owner(uid))
            count = result.scalar_one_or_none() or 0

        stats_ref = fs_service.db.document(f"users/{uid}/store/meta/stats")
        stats_ref.set({
            "product_count": count,
            "update_time": SERVER_TIMESTAMP
        }, merge=True)
        return count

    # ======================================================
    # ✅ 更新评分
    # ======================================================
    @staticmethod
    def update_rating(uid: str, new_rating: float):
        stats_ref = fs_service.db.document(f"users/{uid}/store/meta/stats")
        stats_ref.set({
            "rating": round(new_rating, 2),
            "update_time": SERVER_TIMESTAMP
        }, merge=True)

    # ======================================================
    # ✅ 关注调整
    # ======================================================
    @staticmethod
    def adjust_followers(uid: str, delta: int):
        stats_ref = fs_service.db.document(f"users/{uid}/store/meta/stats")
        stats_ref.set({
            "followers": Increment(delta),
            "update_time": SERVER_TIMESTAMP
        }, merge=True)

    # ======================================================
    # ✅ 信用分调整
    # ======================================================
    @staticmethod
    def adjust_credit(uid: str, delta: int, reason: str = "system update"):
        from app.api.cms.services.store.merchant_service import FirestoreStoreService
        FirestoreStoreService.adjust_credit(uid, delta, reason)

    # ======================================================
    # ✅ 访问量自增
    # ======================================================
    @staticmethod
    def record_visit(uid: str):
        from app.api.cms.services.store.merchant_service import FirestoreStoreService
        FirestoreStoreService.increment_visit(uid)

    # ======================================================
    # ✅ 一键全量同步
    # ======================================================
    @staticmethod
    async def full_sync(uid: str):
        """全量同步 SQL + Firestore 统计"""
        from app.api.cms.services.store.merchant_service import FirestoreStoreService
        count = await StoreServiceStats.sync_product_count(uid)
        FirestoreStoreService.update_stats(uid, {
            "product_count": count,
            "update_time": SERVER_TIMESTAMP
        })
        print(f"✅ 店铺统计同步完成: {uid}")
        return {"uid": uid, "product_count": count}
