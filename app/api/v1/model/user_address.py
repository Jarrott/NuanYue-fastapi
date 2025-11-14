# -*- coding: utf-8 -*-
"""
# @Time    : 2025/11/15 03:35
# @Author  : Pedro
# @File    : user_address.py
# @Software: PyCharm
"""
from datetime import datetime

from sqlalchemy import Column, String, BigInteger, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.pedro.interface import InfoCrud


class UserAddress(InfoCrud):
    """
    📍 用户收货地址 Model
    --------------------
    支持:
    - 多地址
    - 默认地址
    - CRUD 自动继承 InfoCrud
    """

    __tablename__ = "user_addresses"

    # 所属用户
    user_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)

    # 姓名
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)

    # 基础地址
    street: Mapped[str] = mapped_column(String(255), nullable=False)

    # 详细信息（可选）
    building: Mapped[str] = mapped_column(String(255), nullable=True)

    # 邮政编码
    postal_code: Mapped[str] = mapped_column(String(20), nullable=False)

    # 联系电话
    phone: Mapped[str] = mapped_column(String(50), nullable=False)

    # 默认地址
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
