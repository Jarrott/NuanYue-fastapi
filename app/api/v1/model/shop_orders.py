# -*- coding: utf-8 -*-
"""
# @Time    : 2025/11/16 02:11
# @Author  : Pedro
# @File    : shop_orders.py
# @Software: PyCharm
"""

from __future__ import annotations

from sqlalchemy import String, BigInteger, Numeric, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.pedro.interface import InfoCrud


class ShopOrders(InfoCrud):
    """
    🧾 订单主表
    ----------------------
    status:
        PENDING      -> 待支付
        PAID         -> 已支付
        PROCESSING   -> 配货/审核中
        SHIPPED      -> 已发货
        DONE         -> 已完成
        CANCELLED    -> 已取消
    """

    __tablename__ = "shop_orders"

    # 用户（你现在 user_id 用的是字符串 uid）
    user_id: Mapped[str] = mapped_column(String(256), index=True, nullable=False)

    # 订单状态
    status: Mapped[str] = mapped_column(
        String(20), default="PENDING", server_default="PENDING"
    )

    # 价格结构
    subtotal: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    shipping_fee: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    discount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    total: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    payment_method: Mapped[str] = mapped_column(
        String(30), nullable=False, default="WALLET"
    )
    order_no: Mapped[str] = mapped_column(String(30), nullable=False, default=0)
    # 收货地址 ID（引用 user_addresses）
    address_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # 订单下商品（关联明细表）
    items: Mapped[list["ShopOrderItem"]] = relationship(
        "ShopOrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
    )


class ShopOrderItem(InfoCrud):
    """
    📦 订单商品明细表
    """

    __tablename__ = "shop_order_items"

    order_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("shop_orders.id", ondelete="CASCADE"),
        nullable=False,
    )

    product_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    subtotal: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    order: Mapped["ShopOrders"] = relationship(
        "ShopOrders",
        back_populates="items",
    )
