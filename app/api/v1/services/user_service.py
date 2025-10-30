"""
# @Time    : 2025/10/30 10:35
# @Author  : Pedro
# @File    : user_service.py
# @Software: PyCharm
"""
# app/services/user_service.py
from app.api.cms.model.user import User
from app.api.cms.model.user_group import UserGroup
from app.util.invite_services import assign_invite_code, bind_inviter_relation
from app.pedro.enums import GroupLevelEnum


class UserService:

    @staticmethod
    async def create_user_ar(
            *,
            username: str,
            password: str | None = None,
            email: str | None = None,
            name: str | None = None,
            avatar: str | None = None,
            inviter_code: str | None = None,
            group_ids: list[int] | None = None,
    ) -> User:
        """
        使用模型自带的 Active Record 方法，不传 session。
        """
        # 1) 创建用户（模型内部处理 session/commit）
        user = await User.create(
            username=username,
            email=email,
            nickname=name,
            _avatar=avatar,
            commit=True,
        )
        if password:
            await user.set_password(password)  # 内部自己保存/提交

        # 2) 邀请码/邀请关系（内部各自处理 DB）
        await assign_invite_code(user)
        if inviter_code:
            await bind_inviter_relation(user, inviter_code)

        # 3) 分组绑定
        gids = group_ids or [GroupLevelEnum.USER.value]
        # 如果你们的 UserGroup 有批量方法，优先用：
        if hasattr(UserGroup, "bulk_bind"):
            await UserGroup.bulk_bind(user_id=user.id, group_ids=gids)
        else:
            # 逐个创建（内部同样不需要传 session）
            for gid in gids:
                await UserGroup.create(user_id=user.id, group_id=gid, commit=True)

        return user

    @staticmethod
    async def get_by_username(username: str) -> User | None:
        return await User.get(username=username, one=True)

    # @staticmethod
    # async def get_by_email(email: str) -> User | None:
    #     return await User.get(email=email)
