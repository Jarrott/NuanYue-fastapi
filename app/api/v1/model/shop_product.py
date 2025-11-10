"""
# @Time    : 2025/11/10 14:40
# @Author  : Pedro
# @File    : shop_product.py
# @Software: PyCharm
"""
# -*- coding: utf-8 -*-
from sqlalchemy import (
    Column, Integer, String, Numeric, JSON, DateTime, Text, select, Boolean
)
from datetime import datetime
from typing import Optional

from app.pedro.db import get_session
from app.pedro.interface import InfoCrud
from app.pedro.logger import logger


class ShopProduct(InfoCrud):
    """商品模型（Pedro-Core 异步 ORM 版）"""

    __tablename__ = "shop_product"

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_id = Column(String(50), unique=True, nullable=True)
    title = Column(String(255))
    description = Column(Text)
    featured = Column(Boolean, default=False)

    # ✅ 主价体系
    price = Column(Numeric(10, 2))
    discount = Column(Numeric(5, 2))
    rating = Column(Numeric(3, 2))
    stock = Column(Integer)
    category = Column(String(100))
    brand = Column(String(100))
    sku = Column(String(100))

    # ✅ 图片与多媒体
    images = Column(JSON)
    thumbnail = Column(String(500))
    reviews = Column(JSON)

    # ✅ 附加信息
    availability_status = Column(String(100))
    shipping_info = Column(String(200))
    warranty_info = Column(String(200))
    source = Column(String(50), default="dummyjson")
    quantity_available = Column(Integer, default=100)
    lang = Column(String(10), default="en")

    # ✅ 利润体系
    cost_price = Column(Numeric(10, 2), nullable=False, default=0.00, comment="平台采购价")
    sale_price = Column(Numeric(10, 2), nullable=False, default=0.00, comment="卖家采购价")
    retail_price = Column(Numeric(10, 2), nullable=False, default=0.00, comment="终端销售价")
    profit_rate = Column(Numeric(5, 2), default=0.00, comment="利润率")
    profit_amount = Column(Numeric(10, 2), default=0.00, comment="每件商品利润")
    inventory_cost = Column(Numeric(12, 2), default=0.00, comment="库存总成本")
    expected_profit = Column(Numeric(12, 2), default=0.00, comment="预期利润")

    purchase_status = Column(String(20), default="pending", comment="采购状态")

    # ======================================================
    # 🔁 异步 Upsert 操作（全字段版）
    # ======================================================
    @classmethod
    async def upsert_from_external(cls, data: dict):
        """
        异步 Upsert：存在则更新，否则创建
        自动合并 DummyJSON & 自定义采集字段
        """
        external_id = str(data.get("id") or data.get("external_id"))

        # ✅ 自动映射 DummyJSON 字段名差异
        fields = dict(
            external_id=external_id,
            title=data.get("title"),
            description=data.get("description"),
            price=data.get("price") or data.get("retail_price"),
            discount=data.get("discount") or data.get("discountPercentage"),
            rating=data.get("rating"),
            stock=data.get("stock"),
            category=data.get("category"),
            brand=data.get("brand"),
            sku=data.get("sku"),
            thumbnail=data.get("thumbnail") or data.get("image"),
            images=data.get("images"),
            reviews=data.get("reviews"),
            availability_status=data.get("availabilityStatus"),
            shipping_info=data.get("shipping") or data.get("shippingInformation"),
            warranty_info=data.get("warranty") or data.get("warrantyInformation"),
            source=data.get("source", "dummyjson"),
            lang=data.get("lang", "en"),

            # ✅ 新增利润相关字段
            cost_price=data.get("cost_price"),
            sale_price=data.get("sale_price"),
            retail_price=data.get("retail_price"),
            profit_rate=data.get("profit_rate"),
            profit_amount=data.get("profit_amount"),
            inventory_cost=data.get("inventory_cost"),
            expected_profit=data.get("expected_profit"),
        )

        # ✅ 移除 None，避免覆盖已有数据为 null
        clean_fields = {k: v for k, v in fields.items() if v is not None}

        async with get_session() as session:
            result = await session.execute(select(cls).where(cls.external_id == external_id))
            product: Optional[cls] = result.scalar_one_or_none()

            if product:
                for k, v in clean_fields.items():
                    setattr(product, k, v)
                await session.commit()
                await session.refresh(product)
                logger.info(f"🔁 更新商品: {product.title} | 价格: {product.retail_price}")
                return product
            else:
                product = cls(**clean_fields)
                session.add(product)
                await session.commit()
                await session.refresh(product)
                logger.info(f"✅ 新增商品: {product.title} | 价格: {product.retail_price}")
                return product
