from google.cloud.firestore_v1 import SERVER_TIMESTAMP, Increment
from app.extension.google_tools.firebase_admin_service import fs
from app.pedro.response import PedroResponse


class FavoriteStoreService:

    @staticmethod
    async def favorite(uid: str, store_id: str):
        db = fs
        ref = db.collection("users").document(uid)\
                .collection("favorites").document(store_id)

        # 🔥 已经收藏过则直接返回
        snap = ref.get()
        if snap.exists:
            return PedroResponse.fail(msg="已经收藏过该商家")

        # 1️⃣ 写入收藏
        ref.set({
            "created_at": SERVER_TIMESTAMP,
            "type": "store"
        })

        # 2️⃣ 商家 followers +1
        db.collection("users").document(store_id)\
            .collection("store").document("meta")\
            .collection("stats").document("overview")\
            .update({"followers": Increment(1)})

        return PedroResponse.success(msg="收藏成功")

    @staticmethod
    async def unfavorite(uid: str, store_id: str):
        db = fs
        ref = db.collection("users").document(uid)\
                .collection("favorites").document(store_id)

        snap = ref.get()
        # ❌ 没有收藏但点取消 → 直接返回
        if not snap.exists:
            return PedroResponse.fail(msg="当前未收藏，无法取消收藏")

        # 1️⃣ 删除记录
        ref.delete()

        # 2️⃣ followers -1
        db.collection("users").document(store_id)\
            .collection("store").document("meta")\
            .collection("stats").document("overview")\
            .update({"followers": Increment(-1)})

        return PedroResponse.success(msg="取消收藏成功")

    @staticmethod
    async def is_favorited(uid: str, store_id: str):
        db = fs
        doc = db.collection("users").document(uid)\
            .collection("favorites").document(store_id)\
            .get()

        return PedroResponse.success(data={"favorited": doc.exists})

    @staticmethod
    async def list_favorites(uid: str):
        db = fs
        docs = db.collection("users").document(uid)\
            .collection("favorites").stream()

        result = []
        for doc in docs:
            data = doc.to_dict()
            data["store_id"] = doc.id
            result.append(data)

        return PedroResponse.success(data=result)
