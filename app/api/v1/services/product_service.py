# @Time    : 2025/11/10 05:58
# @Author  : Pedro
# @File    : product_firestore_service.py
# @Software: PyCharm

from typing import Optional, List
from google.cloud.firestore_v1 import FieldFilter, And
from firebase_admin import firestore

from app.api.v1.schema.response import ProductResponse


class ProductFirestoreService:
    def __init__(self):
        self.db = firestore.client()
        self.collection = self.db.collection("shop_products")

    async def list_products(
        self,
        keyword: Optional[str] = None,
        category: Optional[str] = None,
        featured: Optional[bool] = None,
        brand: Optional[str] = None,
        order_by: str = "id",
        sort: str = "desc",
        page: int = 1,
        size: int = 10
    ) -> List[ProductResponse]:
        """
        🔎 Firestore 查询商品列表（新版 FieldFilter 语法）
        """

        # 🔹 初始化查询对象
        query = self.collection

        # -----------------------------
        # 🔍 条件过滤 (新版 FieldFilter)
        # -----------------------------
        filters = []
        if category:
            filters.append(FieldFilter("category", "==", category))
        if brand:
            filters.append(FieldFilter("brand", "==", brand))
        if featured is not None:
            filters.append(FieldFilter("featured", "==", featured))

        # ✅ 组合多个条件
        if filters:
            query = query.where(filter=And(filters))

        # 🔍 关键词搜索 (Firestore 不支持模糊查询，只能精确或前缀匹配)
        if keyword:
            query = query.where(filter=FieldFilter("title", ">=", keyword))
            query = query.where(filter=FieldFilter("title", "<=", keyword + "\uf8ff"))

        # -----------------------------
        # 🧭 排序
        # -----------------------------
        direction = firestore.Query.DESCENDING if sort.lower() == "desc" else firestore.Query.ASCENDING
        query = query.order_by(order_by, direction=direction)

        # -----------------------------
        # 📑 分页
        # -----------------------------
        offset = (page - 1) * size
        docs = query.offset(offset).limit(size).stream()

        # -----------------------------
        # 🔄 转换为 Pydantic 模型
        # -----------------------------
        items = [ProductResponse(**doc.to_dict()) for doc in docs]
        return items
