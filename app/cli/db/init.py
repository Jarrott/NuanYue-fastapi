# scripts/init_db.py
import asyncio

from sqlalchemy import select

from app.pedro.db import async_session_factory, engine, Base
from app.pedro.enums import GroupLevelEnum
from app.pedro.manager import manager
from app.api.cms.model.user import User
from app.api.cms.model.group import Group
from app.api.cms.model.user_group import UserGroup



async def init_db(force: bool = False):
    async with engine.begin() as conn:
        if force:
            print("⚠️ Dropping all tables ...")
            await conn.run_sync(Base.metadata.drop_all)

        print("✅ Creating tables ...")
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as session:
        # ✅ 检查是否已经初始化
        exists = await session.scalar(select(User.id).limit(1))
        if exists and not force:
            print("❌ 数据已存在，如需覆盖请使用 force=True")
            return

        print("🚀 创建 Root 管理组 & root 用户 ...")

        # Root 组
        root_group = Group(
            name="Root",
            info="超级管理员",
            level=GroupLevelEnum.ROOT.value
        )
        session.add(root_group)

        # Root 用户
        root = User(username="root")
        session.add(root)
        await session.flush()  # 获取 root.id
        root.password = "123456"

        # Root 用户组绑定
        session.add(UserGroup(
            user_id=root.id,
            group_id=root_group.id
        ))

        # Guest 组
        guest_group = Group(
            name="Guest",
            info="默认游客组",
            level=GroupLevelEnum.GUEST.value,
        )
        session.add(guest_group)

        await session.commit()
        print("✅ 管理员初始化完成")

        # ✅ 同步权限（如果 manager 支持 async）
        if hasattr(manager, "async_sync_permissions"):
            print("🔄 同步权限 ...")
            await manager.async_sync_permissions()
        else:
            print("⚠️ 未检测到 async_sync_permissions，跳过权限同步")


if __name__ == "__main__":
    asyncio.run(init_db(force=False))
