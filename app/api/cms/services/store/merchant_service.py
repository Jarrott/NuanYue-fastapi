"""
# @Time    : 2025/11/13 17:10
# @Author  : Pedro
# @File    : merchant_service.py
# @Software: PyCharm
"""

from datetime import datetime, timezone
from firebase_admin import firestore
from google.cloud.firestore_v1 import transactional

from app.extension.google_tools.firestore import fs_service
from app.extension.google_tools.fs_transaction import SERVER_TIMESTAMP, Increment


class FirestoreStoreService:
    """📊 YOYO Store Firestore Service"""

    @staticmethod
    def stats_ref(uid: str):
        """返回店铺统计文档引用"""
        return fs_service.db.document(f"users/{uid}/store/meta/stats/overview")

    @staticmethod
    def profile_ref(uid: str):
        """返回店铺资料文档引用"""
        return fs_service.db.document(f"users/{uid}/store/profile")

    # =========================================================
    # ✅ 1. 初始化店铺统计文档
    # =========================================================
    @staticmethod
    def init_store_stats(uid: str):
        ref = FirestoreStoreService.stats_ref(uid)
        ref.set({
            "followers": 0,
            "product_count": 0,
            "rating": 0.0,
            "deposit": 0.0,
            "credit_score": 100,
            "visits": {
                "today": 0,
                "total": 0,
                "unique": 0
            },
            "update_time": SERVER_TIMESTAMP
        }, merge=True)

    # =========================================================
    # ✅ 2. 更新统计数据（可局部更新）
    # =========================================================
    @staticmethod
    def update_stats(uid: str, data: dict):
        ref = FirestoreStoreService.stats_ref(uid)
        data["update_time"] = SERVER_TIMESTAMP
        ref.set(data, merge=True)

    # =========================================================
    # ✅ 3. 访客计数（今日 / 总数）
    # =========================================================
    @staticmethod
    def increment_visit(uid: str):
        ref = FirestoreStoreService.stats_ref(uid)
        ref.set({
            "visits.today": Increment(1),
            "visits.total": Increment(1),
            "update_time": SERVER_TIMESTAMP
        }, merge=True)

    # =========================================================
    # ✅ 4. 信用分调整
    # =========================================================
    @staticmethod
    def adjust_credit(uid: str, delta: int, reason: str = "system update"):
        stats_ref = FirestoreStoreService.stats_ref(uid)
        history_ref = fs_service.db.collection(f"users/{uid}/store/meta/credit_history").document()

        @transactional
        def _tx(transaction):
            # 更新 credit_score
            stats_snapshot = stats_ref.get(transaction=transaction)
            current_score = stats_snapshot.get("credit_score") or 100
            new_score = max(0, min(1000, current_score + delta))
            transaction.update(stats_ref, {
                "credit_score": new_score,
                "update_time": SERVER_TIMESTAMP
            })
            # 写入信用变动历史
            transaction.set(history_ref, {
                "delta": delta,
                "reason": reason,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "score_after": new_score
            })

        _tx(fs_service.db.transaction())

    # =========================================================
    # ✅ 5. 读取完整店铺概览（结合 profile + stats）
    # =========================================================
    @staticmethod
    def get_store_overview(uid: str) -> dict:
        profile_ref = FirestoreStoreService.profile_ref(uid)
        stats_ref = FirestoreStoreService.stats_ref(uid)
        profile = profile_ref.get().to_dict() or {}
        stats = stats_ref.get().to_dict() or {}
        return {**profile, **stats}
