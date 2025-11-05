"""
# @Time    : 2025/10/28 11:50
# @Author  : Pedro
# @File    : shop_product.py
# @Software: PyCharm
"""
# -*- coding: utf-8 -*-
"""
@Time    : 2025/10/28 19:04
@Author  : Pedro
@File    : shop_product.py
@Software: PyCharm
"""
from sqlalchemy import (
    Column, Integer, String, Numeric, JSON, DateTime, Text, select, Boolean
)
from datetime import datetime
from typing import Optional

from app.pedro.db import get_session
from app.pedro.interface import InfoCrud  # ✅ 异步基类（Pedro-Core 通用）
from app.pedro.logger import logger


class ShopProduct(InfoCrud):
    """商品模型（异步 ORM 版）"""

    __tablename__ = "shop_product"

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_id = Column(String(50), unique=True, nullable=True)
    title = Column(String(255))
    description = Column(Text)
    featured = Column(Boolean, default=False)
    price = Column(Numeric(10, 2))
    discount = Column(Numeric(5, 2))
    rating = Column(Numeric(3, 2))
    stock = Column(Integer)
    category = Column(String(100))
    brand = Column(String(100))
    sku = Column(String(100))
    images = Column(JSON)
    thumbnail = Column(String(500))
    reviews = Column(JSON)
    availability_status = Column(String(100))
    shipping_info = Column(String(200))
    warranty_info = Column(String(200))
    source = Column(String(50), default="dummyjson")
    quantity_available = Column(Integer, default=100)
    lang = Column(String(10), default="en")

    # ======================================================
    # 🔁 异步 Upsert 操作
    # ======================================================
    @classmethod
    async def upsert_from_external(cls, data: dict):
        """
        异步 Upsert（存在则更新，否则创建）
        """
        external_id = str(data["id"])
        fields = dict(
            external_id=external_id,
            title=data.get("title"),
            description=data.get("description"),
            price=data.get("price"),
            discount=data.get("discountPercentage"),
            rating=data.get("rating"),
            stock=data.get("stock"),
            category=data.get("category"),
            brand=data.get("brand"),
            sku=data.get("sku"),
            images=data.get("images"),
            thumbnail=data.get("thumbnail"),
            reviews=data.get("reviews"),
            availability_status=data.get("availabilityStatus"),
            shipping_info=data.get("shippingInformation"),
            warranty_info=data.get("warrantyInformation"),
            source="dummyjson",
            lang=data.get("lang", "en"),
            updated_at=datetime.utcnow(),
        )

        async with get_session() as session:
            result = await session.execute(select(cls).where(cls.external_id == external_id))
            product: Optional[cls] = result.scalar_one_or_none()

            if product:
                for k, v in fields.items():
                    setattr(product, k, v)
                await session.commit()
                await session.refresh(product)
                logger.info(f"🔁 更新商品: {product.title}")
                return product
            else:
                product = cls(**fields)
                session.add(product)
                await session.commit()
                await session.refresh(product)
                logger.info(f"✅ 新增商品: {product.title}")
                return product
