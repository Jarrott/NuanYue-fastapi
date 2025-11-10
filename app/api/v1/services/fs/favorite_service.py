# @Time    : 2025/11/10 18:00
# @Author  : Pedro
# @File    : favorite_service_fs.py
# @Software: PyCharm
"""
Pedro-Core ❤️ 喜欢功能（Firestore版）
---------------------------------------
✅ Firestore 原子结构存储
✅ 用户实时收藏/取消
✅ 自动同步前端状态
"""
from datetime import datetime
from app.extension.google_tools.firestore import fs_service as fs
from app.extension.google_tools.fs_transaction import SERVER_TIMESTAMP
from app.pedro.response import PedroResponse
from google.cloud import firestore


class FavoriteServiceFS:
    @staticmethod
    async def toggle(uid: str, product: dict):
        """
        ❤️ 添加或取消收藏
        product = {"id": "123", "title": "...", "image": "...", "price": 4.0}
        """
        fav_ref = fs.db.document(f"users/{uid}/favorites/{product['id']}")
        snap = fav_ref.get()

        if snap.exists:
            fav_ref.delete()
            # 可选：同步减少产品喜欢数
            fs.db.document(f"products/{product['id']}/meta/likes").update({
                "count": firestore.Increment(-1)
            })
            return PedroResponse.success({"liked": False}, "已取消喜欢")
        else:
            fav_ref.set({
                "product_id": product["id"],
                "title": product.get("title"),
                "image": product.get("thumbnail"),
                "price": product.get("price"),
                "created_at": SERVER_TIMESTAMP
            })
            # 可选：同步增加产品喜欢数
            fs.db.document(f"products/{product['id']}/meta/likes").set({
                "count": firestore.Increment(1)
            }, merge=True)
            return PedroResponse.success({"liked": True}, "已添加喜欢")

    @staticmethod
    async def list(uid: str, limit: int = 20):
        """
        ❤️ 获取用户喜欢列表
        """
        docs = fs.db.collection(f"users/{uid}/favorites").order_by(
            "created_at", direction=firestore.Query.DESCENDING
        ).limit(limit).stream()

        items = [doc.to_dict() for doc in docs]
        return PedroResponse.success(items)
