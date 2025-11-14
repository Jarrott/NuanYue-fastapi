import asyncio
from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from app.extension.google_tools.firebase_admin_service import fs
from app.pedro.response import PedroResponse


class StoreServiceFS:

    @staticmethod
    async def _fetch_store_stats(uid: str):
        """读取 meta/stats/overview 作为补充字段"""
        ref = fs.collection("users").document(uid).collection("store") \
            .document("meta").collection("stats").document("overview")

        snap = ref.get()
        return snap.to_dict() if snap.exists else {}

    @staticmethod
    async def list_stores(limit: int = 20):
        db = fs

        query = (
            db.collection_group("store")
            .where(filter=FieldFilter("status", "==", "approved"))
            .order_by("create_time", direction=firestore.Query.DESCENDING)
            .limit(limit)
        )

        docs = query.stream()

        stores = []
        tasks = []

        for doc in docs:
            if doc.id != "profile":
                continue

            data = doc.to_dict()
            uid = doc.reference.parent.parent.id  # 反推 user id
            data["uid"] = uid

            # 🔥 异步读取统计信息
            tasks.append(StoreServiceFS._fetch_store_stats(uid))

            stores.append(data)

        # 并发等待所有 stats 数据返回
        stats_results = await asyncio.gather(*tasks)

        # 🔗 合并 stats 数据到 store profile
        for store, stats in zip(stores, stats_results):
            store.update({"stats": stats})

        print(f"🔥 Loaded {len(stores)} stores with stats merged")
        return stores
