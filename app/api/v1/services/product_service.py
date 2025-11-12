# -*- coding: utf-8 -*-
"""
# @Time    : 2025/11/10 22:31
# @Author  : Pedro
# @File    : product_service.py
# @Software: PyCharm
"""
from typing import Optional, Tuple, List

from firebase_admin import firestore

from app.api.v1.model.shop_product import ShopProduct
from app.extension.google_tools.firestore import fs_service
from app.extension.google_tools.fs_transaction import SERVER_TIMESTAMP, Increment
from app.pedro.response import PedroResponse


class ProductService:

    """
    🧩 Pedro-Core 商品服务层
    ---------------------------------------------
    ✅ 基于 BaseCrud.paginate() 的统一分页查询
    ✅ 支持关键字模糊搜索、多条件过滤、排序
    ✅ 结果可直接传入 PedroResponse.page()
    """

    @staticmethod
    async def list_products(
            *,
            uid: Optional[str] = None,  # ✅ 新增用户ID
            keyword: Optional[str] = None,
            category: Optional[str] = None,
            brand: Optional[str] = None,
            featured: Optional[bool] = None,
            order_by: str = "id",
            sort: str = "desc",
            page: int = 1,
            size: int = 10,
    ) -> Tuple[List[dict], int]:
        """
        🔍 获取商品列表（支持搜索、筛选、分页 + 是否收藏）
        ---------------------------------------------
        :param uid: 用户ID（可选，用于判断收藏状态）
        :return: (items, total)
        """

        filters = {
            "category": category,
            "brand": brand,
            "featured": featured,
        }
        keyword_fields = ["title", "description", "brand"]

        # 🔸 ORM 分页查询
        items, total = await ShopProduct.paginate(
            page=page,
            size=size,
            filters=filters,
            keyword=keyword,
            keyword_fields=keyword_fields,
            order_by=order_by,
            sort=sort,
        )

        # 🔸 如果未登录用户，直接返回原结果
        if not uid:
            return [
                {
                    "id": p.id,
                    "title": p.title,
                    "price": float(p.price),
                    "stock": int(p.stock or 0),
                    "images": p.images,
                    "brand": p.brand,
                    "category": p.category,
                    "thumbnail": p.thumbnail,
                    "sale_price": p.sale_price,
                    "is_liked": False,  # 匿名用户一律 False
                }
                for p in items
            ], total

        # ✅ 仅查询当前登录用户的收藏集合
        try:
            user_fav_col = f"users/{uid}/favorites"
            docs = fs_service.db.collection(user_fav_col).stream()
            user_fav_ids = {doc.id for doc in docs if doc.exists}
            liked_set = {str(pid) for pid in user_fav_ids}
        except Exception as e:
            print(f"[WARN] Firestore 收藏读取失败: {e}")
            liked_set = set()

        results = []
        for p in items:
            is_liked = str(p.id) in liked_set
            results.append({
                "id": p.id,
                "title": p.title,
                "price": float(p.price),
                "stock": int(p.stock or 0),
                "images": p.images,
                "brand": p.brand,
                "category": p.category,
                "is_liked": is_liked,
                "thumbnail": p.thumbnail,
                "sale_price": p.sale_price,
            })


        return results, total

    @staticmethod
    async def get_detail(uid: str, product_id: int):
        """
        🛍 获取商品详情 + 是否已喜欢
        """
        # Step 1: SQL 查商品详情
        product = await ShopProduct.get(id=product_id)
        if not product:
            return PedroResponse.fail(msg="商品不存在")

        # Step 2: Firestore 检查用户是否喜欢
        fav_path = f"users/{uid}/favorites/{product_id}"
        fav_doc = await fs_service.get(fav_path)
        is_liked = bool(fav_doc)

        # Step 3: 返回整合结果
        data = {
            "id": product.id,
            "title": product.title,
            "price": float(product.price),
            "stock": int(product.stock),
            "images": product.images,
            "rating": product.rating,
            "discount": product.discount,
            "thumbnail": product.thumbnail,
            "is_liked": is_liked,  # ✅ 关键字段
        }
        return data

    # ==============================================================
    # 🔍 搜索商品 + 记录搜索历史
    # ==============================================================
    @staticmethod
    async def search_products(uid: int, keyword: str, limit: int = 20):
        """
        🔍 搜索商品（模糊匹配 title / description / brand）
        -------------------------------------------------
        Firestore 路径:
            users/{uid}/search_history/{keyword}
        """
        keyword = (keyword or "").strip()
        if not keyword:
            return PedroResponse.fail(msg="搜索关键词不能为空")

        # 1️⃣ ORM 模糊搜索（调用 BaseCrud.filter_like）
        products = await ShopProduct.filter_like(
            keyword=keyword,
            fields=["title", "description", "brand"],
            limit=limit,
            order_by="id",
            sort="desc",
        )

        # 2️⃣ Firestore 写入搜索历史（去重 + 自增）
        path = f"users/{uid}/search_history/{keyword}"
        try:
            existing = await fs_service.get(path)
            if existing:
                await fs_service.update(path, {
                    "count": Increment(1),
                    "last_search_time": SERVER_TIMESTAMP
                })
            else:
                await fs_service.set(path, {
                    "keyword": keyword,
                    "count": 1,
                    "last_search_time": SERVER_TIMESTAMP
                })
        except Exception as e:
            print(f"[WARN] 写入搜索历史失败: {e}")

        fav_docs = await fs_service.list_documents(f"users/{uid}/favorites")
        fav_ids = {doc.id for doc in fav_docs}
        # 3️⃣ 构建响应
        data = [
            {
                "id": p.id,
                "title": p.title,
                "price": float(p.price),
                "stock": int(p.stock or 0),
                "images": p.images,
                "thumbnail": p.thumbnail,
                "rating": getattr(p, "rating", None),
                "is_liked": bool(str(p.id) in fav_ids),  # ✅ 确保为布尔值 True/False
                "discount": getattr(p, "discount", None),
            }
            for p in products
        ]
        msg = "搜索成功" if data else "暂无匹配商品"
        return PedroResponse.success(data=data, msg=msg)

    # ==============================================================
    # 🧠 获取搜索历史
    # ==============================================================
    @staticmethod
    async def list_search_history(uid: str, limit: int = 10):
        """
        🧠 获取最近搜索记录
        -------------------------------------------------
        Firestore 路径:
            users/{uid}/search_history
        """
        path = f"users/{uid}/search_history"
        try:
            query = (
                fs_service.db.collection(path)
                .order_by("last_search_time", direction=firestore.firestore.Query.DESCENDING)
                .limit(limit)
            )
            docs = query.stream()
            history = [
                {"keyword": doc.id, **doc.to_dict()}
                for doc in docs if doc.exists
            ]
            return history
        except Exception as e:
            print(f"[ERROR] 获取搜索记录失败: {e}")
            return PedroResponse.fail(msg="搜索记录获取失败")

    # ==============================================================
    # 🧹 清空搜索历史
    # ==============================================================
    @staticmethod
    async def clear_search_history(uid: str):
        """
        🧹 清空用户搜索历史记录
        -------------------------------------------------
        Firestore 路径:
            users/{uid}/search_history/*
        """
        path = f"users/{uid}/search_history"
        try:
            docs = fs_service.db.collection(path).stream()
            batch = fs_service.db.batch()
            count = 0
            for doc in docs:
                batch.delete(doc.reference)
                count += 1
            batch.commit()
            return PedroResponse.success(msg=f"已清空 {count} 条搜索记录")
        except Exception as e:
            print(f"[ERROR] 清空搜索记录失败: {e}")
            return PedroResponse.fail(msg="清空搜索记录失败")