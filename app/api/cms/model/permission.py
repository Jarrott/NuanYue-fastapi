"""
# @Time    : 2025/10/28 2:08
# @Author  : Pedro
# @File    : permission.py
# @Software: PyCharm
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.pedro.model import Permission  as LinPermission
from app.pedro.db import Base

class Permission(LinPermission):

    @classmethod
    async def select_by_group_id(
        cls, db: AsyncSession, group_id: int, group_permission_model
    ) -> List["Permission"]:
        """
        传入用户组Id ，根据 Group-Permission 关联表获取权限列表
        """
        subq = (
            select(group_permission_model.permission_id)
            .where(group_permission_model.group_id == group_id)
        )
        stmt = select(cls).where(cls.id.in_(subq)).where(
            cls.soft.is_(True), cls.mount.is_(True)
        )
        res = await db.execute(stmt)
        return res.scalars().all()

    @classmethod
    async def select_by_group_ids(
        cls, db: AsyncSession, group_ids: List[int], group_permission_model
    ) -> List["Permission"]:
        """
        传入用户组Id列表 ，根据 Group-Permission 关联表获取权限列表
        """
        subq = (
            select(group_permission_model.permission_id)
            .where(group_permission_model.group_id.in_(group_ids))
        )
        stmt = select(cls).where(cls.id.in_(subq)).where(
            cls.soft.is_(True), cls.mount.is_(True)
        )
        res = await db.execute(stmt)
        return res.scalars().all()

    @classmethod
    async def select_by_group_ids_and_module(
        cls,
        db: AsyncSession,
        group_ids: List[int],
        module: str,
        group_permission_model,
    ) -> List["Permission"]:
        """
        传入用户组Id列表和模块名，根据 Group-Permission 关联表获取权限列表
        """
        subq = (
            select(group_permission_model.permission_id)
            .where(group_permission_model.group_id.in_(group_ids))
        )
        stmt = (
            select(cls)
            .where(cls.id.in_(subq))
            .where(cls.soft.is_(True), cls.mount.is_(True))
            .where(cls.module == module)
        )
        res = await db.execute(stmt)
        return res.scalars().all()
