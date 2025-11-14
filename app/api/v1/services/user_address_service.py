# -*- coding: utf-8 -*-
"""
# @Time    : 2025/11/15 03:22
# @Author  : Pedro
# @File    : address_service.py
# @Software: PyCharm
"""

from sqlalchemy import select, update, delete
from app.pedro.db import async_session_factory
from app.pedro.response import PedroResponse
from app.api.v1.model.user_address import UserAddress


class UserAddressService:

    @staticmethod
    async def list_addresses(uid: str):
        async with async_session_factory() as session:
            result = await session.execute(
                select(UserAddress)
                .where(UserAddress.user_id == uid)
                .order_by(UserAddress.is_default.desc(), UserAddress.update_time.desc())
            )
            return result.scalars().all()

    @staticmethod
    async def get_address_detail(uid: str, address_id: int):
        async with async_session_factory() as session:
            result = await session.execute(
                select(UserAddress).where(
                    UserAddress.id == address_id,
                    UserAddress.user_id == uid
                )
            )
            obj = result.scalar_one_or_none()

            if not obj:
                raise ValueError("Address not found")

            return obj

    @staticmethod
    async def add_address(uid: str, data: dict):
        async with async_session_factory() as session:
            if data.get("is_default"):
                await session.execute(
                    update(UserAddress)
                    .where(UserAddress.user_id == uid)
                    .values(is_default=False)
                )

            obj = UserAddress(user_id=uid, **data)
            session.add(obj)
            await session.commit()
            await session.refresh(obj)

            return PedroResponse.success(obj)

    @staticmethod
    async def update_address(uid: str, address_id: int, data: dict):
        async with async_session_factory() as session:
            result = await session.execute(
                select(UserAddress).where(
                    UserAddress.id == address_id,
                    UserAddress.user_id == uid
                )
            )
            obj = result.scalar_one_or_none()
            if not obj:
                raise ValueError("Address not found")

            for k, v in data.items():
                setattr(obj, k, v)

            await session.commit()
            return obj

    @staticmethod
    async def set_default(uid: str, address_id: int):
        async with async_session_factory() as session:
            await session.execute(
                update(UserAddress)
                .where(UserAddress.user_id == uid)
                .values(is_default=False)
            )
            await session.execute(
                update(UserAddress)
                .where(UserAddress.id == address_id, UserAddress.user_id == uid)
                .values(is_default=True)
            )
            await session.commit()
