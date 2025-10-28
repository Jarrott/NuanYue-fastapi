"""
# @Time    : 2025/10/28 2:14
# @Author  : Pedro
# @File    : group_permission.py
# @Software: PyCharm
"""
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.pedro.model import GroupPermission as LinGroupPermission
from app.pedro.db import Base


class GroupPermission(LinGroupPermission):

    @classmethod
    async def delete_batch_by_group_id_and_permission_ids(
            cls,
            db: AsyncSession,
            group_id: int,
            permission_ids: List[int],
            commit: bool = False,
    ) -> None:
        """
        批量删除指定 group_id 的多个权限绑定关系
        """
        stmt = (
            delete(cls)
            .where(cls.group_id == group_id)
            .where(cls.permission_id.in_(permission_ids))
        )
        await db.execute(stmt)
        if commit:
            await db.commit()
