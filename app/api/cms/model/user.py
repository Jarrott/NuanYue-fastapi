from copy import deepcopy

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.pedro.model import User as LinUser
from app.pedro.db import Base, async_session_factory
from app.util.jsonb_update import JsonbManager
from typing import List


class User(LinUser):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._exclude = ["delete_time", "create_time", "is_deleted", "update_time"]

    # ===========================
    # 异步方法
    # ===========================


class User(LinUser):

    async def jset(self, key, value):
        async with async_session_factory() as session:
            await JsonbManager.set(session, self.__class__, self.id, key, value)
            await session.commit()

    async def jinc(self, key, amount):
        async with async_session_factory() as session:
            await JsonbManager.inc(session, self.__class__, self.id, key, amount)
            await session.commit()

    async def jremove(self, key):
        async with async_session_factory() as session:
            await JsonbManager.remove(session, self.__class__, self.id, key)
            await session.commit()

    async def jpush(self, key, value):
        async with async_session_factory() as session:
            await JsonbManager.append(session, self.__class__, self.id, key, value)
            await session.commit()

    async def jpush_unique_path(self, path: str, value: dict, unique_fields=None, limit=5):
        if not isinstance(value, dict):
            return

        keys = path.split(".")
        extra = deepcopy(self.extra) or {}

        # descend path
        data = extra
        for k in keys[:-1]:
            data = data.setdefault(k, {})

        arr_key = keys[-1]
        array = data.get(arr_key, [])
        if not isinstance(array, list):
            array = []

        unique_fields = unique_fields or ["device", "browser", "os"]
        sig = "|".join(str(value.get(f, "")) for f in unique_fields)

        # dedupe
        for d in array:
            if isinstance(d, dict):
                if "|".join(str(d.get(f, "")) for f in unique_fields) == sig:
                    return

        array.insert(0, value)
        array = array[:limit]

        # write back only
        data[arr_key] = array
        self.extra = extra  # ✅ 只更新 ORM 对象，不 commit，不 add

    @classmethod
    async def update_json(cls, user_id: int, key: str, value: any):
        async with async_session_factory() as session:
            await JsonbManager.set(session, cls, user_id, key, value)
            await session.commit()

    @classmethod
    async def inc_json(cls, user_id: int, key: str, amount: float):
        async with async_session_factory() as session:
            await JsonbManager.inc(session, cls, user_id, key, amount)
            await session.commit()

    @classmethod
    async def add_login_device(cls, user_id: int, device: dict):
        async with async_session_factory() as session:
            user = await session.scalar(select(cls).where(cls.id == user_id))
            if not user:
                return

            await user.jpush_unique_path("sensitive.login_devices", device)
            await session.commit()

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
