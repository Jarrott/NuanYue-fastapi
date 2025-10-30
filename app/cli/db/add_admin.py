import asyncio
from sqlalchemy import select

from app.api.v1.services.user_service import UserService
from app.pedro.db import async_session_factory
from app.pedro.model import GroupLevelEnum,Group,UserGroup,User

ADMIN_USERNAME = "root"
ADMIN_PASSWORD = "123456"


async def ensure_admin_group(session):
    """确保 Root 管理组存在"""
    result = await session.execute(
        select(Group).where(Group.level == GroupLevelEnum.ROOT.value)
    )
    group = result.scalar_one_or_none()

    if not group:
        group = Group(
            name="Root",
            info="超级管理员",
            level=GroupLevelEnum.ROOT.value
        )
        session.add(group)
        await session.flush()
        print(f"✅ 创建 Root 管理组成功：group_id={group.id}")

    return group


async def add_admin():
    async with async_session_factory() as session:
        # ✅ 检查管理员是否存在
        res = await session.execute(select(User).where(User.username == ADMIN_USERNAME))
        root = res.scalar_one_or_none()

        # ✅ 检查/创建 Root 组
        root_group = await ensure_admin_group(session)

        if not root:
            # ✅ 用你已有的 Service 创建
            await UserService.create_user_ar(
                username=ADMIN_USERNAME,
                password=ADMIN_PASSWORD,
                inviter_code=None,
                group_ids=[root_group.id],
            )
            print(f"✅ 管理员 {ADMIN_USERNAME} 已创建")

        else:
            print(f"ℹ️ 管理员 {ADMIN_USERNAME} 已存在")

            # ✅ 确保组绑定存在
            result = await session.execute(
                select(UserGroup).where(
                    UserGroup.user_id == root.id,
                    UserGroup.group_id == root_group.id
                )
            )
            ug = result.scalar_one_or_none()
            if not ug:
                session.add(UserGroup(user_id=root.id, group_id=root_group.id))
                await session.commit()
                print("✅ 已补齐管理员权限")
            else:
                print("✅ 管理员权限正常，无需处理")

        await session.commit()


if __name__ == "__main__":
    asyncio.run(add_admin())
