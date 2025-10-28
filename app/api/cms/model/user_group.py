"""
# @Time    : 2025/10/28 2:07
# @Author  : Pedro
# @File    : user_group.py
# @Software: PyCharm
"""
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.pedro.model import UserGroup as LinUserGroup
from app.pedro.db import Base

class UserGroup(LinUserGroup):

    @classmethod
    async def delete_batch_by_user_id_and_group_ids(
            cls,
            db: AsyncSession,
            user_id: int,
            group_ids: List[int],
            commit: bool = False,
    ) -> None:
        """
        批量删除用户与指定分组的关联关系
        """
        stmt = (
            delete(cls)
            .where(cls.user_id == user_id)
            .where(cls.group_id.in_(group_ids))
        )
        await db.execute(stmt)
        if commit:
            await db.commit()
