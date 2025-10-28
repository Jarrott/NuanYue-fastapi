"""
# @Time    : 2025/10/28 2:17
# @Author  : Pedro
# @File    : group.py
# @Software: PyCharm
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.pedro.model import Group as LinGroup
from app.pedro.db import Base


class Group(LinGroup):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._exclude = ["delete_time", "create_time", "update_time", "is_deleted"]

    @classmethod
    async def select_by_user_id(
            cls,
            db: AsyncSession,
            user_id: int,
            user_group_model,
            user_model,
    ) -> List["Group"]:
        """
        根据用户Id，通过 User-Group 关联表 获取所属用户组对象列表
        """
        # 🔹 子查询：从 user_group 取出 group_id
        subq = (
            select(user_group_model.group_id)
            .join(user_model, user_model.id == user_group_model.user_id)
            .where(user_model.delete_time.is_(None))
            .where(user_model.id == user_id)
        )

        # 🔹 主查询：通过 group_id 查询 Group 表
        stmt = (
            select(cls)
            .where(cls.soft.is_(True))
            .where(cls.id.in_(subq))
        )

        result = await db.execute(stmt)
        return result.scalars().all()
