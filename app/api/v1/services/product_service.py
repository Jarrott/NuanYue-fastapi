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
        keyword: Optional[str] = None,
        category: Optional[str] = None,
        brand: Optional[str] = None,
        featured: Optional[bool] = None,
        order_by: str = "id",
        sort: str = "desc",
        page: int = 1,
        size: int = 10,
    ) -> Tuple[List[ShopProduct], int]:
        """
        🔍 获取商品列表（支持搜索、筛选、分页）
        ---------------------------------------------
        :param keyword: 搜索关键词（匹配 title / description / brand）
        :param category: 商品分类
        :param brand: 品牌
        :param featured: 是否推荐商品
        :param order_by: 排序字段
        :param sort: 排序方向（asc / desc）
        :param page: 页码
        :param size: 每页数量
        :return: (items, total)
        """

        # 🔸 构建过滤条件
        filters = {
            "category": category,
            "brand": brand,
            "featured": featured,
        }

        # 🔸 关键字模糊搜索字段
        keyword_fields = ["title", "description", "brand"]

        # 🔸 调用通用分页方法
        items, total = await ShopProduct.paginate(
            page=page,
            size=size,
            filters=filters,
            keyword=keyword,
            keyword_fields=keyword_fields,
            order_by=order_by,
            sort=sort,
        )

        return items, total

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

        # 3️⃣ 构建响应
        data = [
            {
                "id": p.id,
                "title": p.title,
                "price": float(p.price),
                "stock": int(p.stock or 0),
                "images": p.images,
                "rating": getattr(p, "rating", None),
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