"""
# @Time    : 2025/10/30 10:35
# @Author  : Pedro
# @File    : user_service.py
# @Software: PyCharm
"""
import random

# app/services/user_service.py
from app.api.cms.model.user import User
from app.api.cms.model.user_group import UserGroup
from app.extension.redis.redis_client import rds
from app.pedro.exception import ParameterError
from app.util.invite_services import assign_invite_code, bind_inviter_relation
from app.pedro.enums import GroupLevelEnum


class UserService:

    @staticmethod
    async def create_user_ar(
            *,
            username: str,
            password: str | None = None,
            email: str | None = None,
            avatar: str | None = None,
            inviter_code: str | None = None,
            group_ids: list[int] | None = None,
            nickname: str | None = None,
    ) -> User:
        """
        使用模型自带的 Active Record 方法，不传 session。
        """
        # 1) 创建用户（模型内部处理 session/commit）
        user = await User.create(
            username=username,
            email=email,
            nickname=nickname,
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

    @staticmethod
    async def send_reset_code(email: str):
        code = str(random.randint(100000, 999999))
        key = f"reset_pwd:{email}"

        redis = await rds.instance()
        await redis.setex(key, 300, code)  # 5分钟有效

        # TODO: 替换为你的邮件服务
        print(f"[DEBUG] 发送密码重置验证码 {code} 到邮箱 {email}")
        return code

    # @staticmethod
    # async def get_by_email(email: str) -> User | None:
    #     return await User.get(email=email)

    async def reset_password(email: str, code: str, new_password: str):
        redis = await rds.instance()
        key = f"reset_pwd:{email}"
        real_code = await redis.get(key)

        if not real_code or real_code.decode() != code:
            raise ParameterError("验证码无效或已过期")

        user = await User.get(email=email)
        if not user:
            raise ParameterError("该邮箱未注册")

        # ✅ 加密新密码
        hashed = user.generate_password_hash(new_password)

        await user.update(password=hashed, commit=True)

        # ✅ 删除验证码
        await redis.delete(key)
        return True
