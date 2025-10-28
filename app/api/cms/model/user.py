from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.pedro.model import User as LinUser
from app.pedro.db import Base
from typing import List


class User(LinUser):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._exclude = ["delete_time", "create_time", "is_deleted", "update_time"]

    # ===========================
    # 异步方法
    # ===========================

    @classmethod
    async def count_by_username(cls, db: AsyncSession, username: str) -> int:
        stmt = (
            select(func.count(cls.id))
            .where(cls.username == username)
            .where(cls.is_deleted == False)
        )
        result = await db.execute(stmt)
        return result.scalar_one()

    @classmethod
    async def count_by_email(cls, db: AsyncSession, email: str) -> int:
        stmt = (
            select(func.count(cls.id))
            .where(cls.email == email)
            .where(cls.is_deleted == False)
        )
        result = await db.execute(stmt)
        return result.scalar_one()

    @classmethod
    async def select_page_by_group_id(
        cls,
        db: AsyncSession,
        group_id: int,
        root_group_id: int,
        user_group_model,
    ) -> List["User"]:
        """
        通过分组id分页获取用户数据
        """
        subquery = (
            select(user_group_model.user_id)
            .where(user_group_model.group_id == group_id)
            .where(user_group_model.group_id != root_group_id)
        )

        stmt = select(cls).where(cls.id.in_(subquery))
        result = await db.execute(stmt)
        return result.scalars().all()

    async def reset_password(self, new_password: str):
        self.password = new_password

    async def change_password(self, old_password: str, new_password: str) -> bool:
        if self.check_password(old_password):
            self.password = new_password
            return True
        return False
