# -*- coding: utf-8 -*-
"""
# @Time    : 2025/11/16
# @Author  : Pedro
# @File    : cart_service.py
# @Software: PyCharm
"""

import json
from sqlalchemy import select

from app.extension.redis.redis_client import rds
from app.pedro.db import async_session_factory
from app.api.v1.model.shop_product import ShopProduct


class CartService:
    """
    🛒 普通用户购物车（Redis 实时存储）
    """

    @staticmethod
    async def _key(uid: str) -> str:
        return f"cart:{uid}"  # 保证 uid 类型为 str，避免 cart:1 vs cart:'1' 不一致

    # 1️⃣ 添加商品到购物车
    @staticmethod
    async def add_to_cart(uid: str, product_id: int, qty: int = 1):
        r = await rds.instance()
        key = await CartService._key(uid)

        existing = await r.hget(key, str(product_id))

        if existing:
            data = json.loads(existing)
            data["qty"] += qty
        else:
            data = {"qty": qty}

        await r.hset(key, str(product_id), json.dumps(data))
        return data

    # 2️⃣ 更新购物车数量
    @staticmethod
    async def update_quantity(uid: str, product_id: int, qty: int):
        r = await rds.instance()
        key = await CartService._key(uid)

        if qty <= 0:
            await r.hdel(key, str(product_id))
            return {"status": "removed"}

        await r.hset(key, str(product_id), json.dumps({"qty": qty}))
        return {"qty": qty}

    # 3️⃣ 删除商品
    @staticmethod
    async def remove_item(uid: str, product_id: str):
        r = await rds.instance()
        key = await CartService._key(uid)
        await r.hdel(key, str(product_id))
        return {"status": "removed"}

    # 4️⃣ 清空购物车
    @staticmethod
    async def clear(uid: str):
        r = await rds.instance()
        await r.delete(await CartService._key(uid))
        return {"status": "cleared"}

    # 5️⃣ 获取购物车详情（带价格）
    @staticmethod
    async def get_cart(uid: str):
        r = await rds.instance()
        key = await CartService._key(uid)

        data = await r.hgetall(key)

        if not data:
            return {"items": [], "total": 0}

        items = []
        total = 0

        async with async_session_factory() as session:
            for product_id, json_val in data.items():
                cart_data = json.loads(json_val)

                result = await session.execute(
                    select(ShopProduct).where(ShopProduct.id == int(product_id))
                )
                product = result.scalar_one_or_none()

                if not product:
                    continue  # 商品下架也不会报错

                subtotal = float(product.price) * cart_data["qty"]
                total += subtotal

                items.append({
                    "product_id": product.id,
                    "title": product.title,
                    "price": float(product.price),
                    "thumbnail": product.thumbnail,
                    "quantity": cart_data["qty"],
                    "subtotal": subtotal
                })

        return {"items": items, "total": round(total, 2)}
