# -*- coding: utf-8 -*-
"""
Pedro-Core 用户模型扩展
支持：
✅ 异步数据库
✅ 密码校验 / 哈希
✅ 管理员标识
✅ 头像拼接
✅ 统一错误体系
"""
import hashlib
import os
from typing import Optional
from sqlalchemy import select, func
from passlib.context import CryptContext
from werkzeug.security import generate_password_hash as gph, check_password_hash as cph

from app.pedro.db import async_session_factory, BaseModel
from app.pedro.enums import GroupLevelEnum
from app.pedro.interface import (
    AbstractUser,
    AbstractGroup,
    AbstractPermission,
    AbstractUserGroup,
    AbstractUserIdentity,
    AbstractGroupPermission,
)
from app.pedro.exception import ParameterError, NotFound, UnAuthentication
from app.config.settings_manager import get_current_settings

# ======================================================
# 🧩 User Model
# ======================================================
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def generate_password_hash(raw: str) -> str:
    return pwd_context.hash(raw)


def check_password_hash(raw: str, hashed: str) -> bool:
    return pwd_context.verify(raw, hashed)


class User(AbstractUser, BaseModel):
    __table_args__ = {'extend_existing': True}

    # ======================================================
    # 🔐 密码相关
    # ======================================================
    async def set_password(self, raw: str) -> None:
        """设置密码（异步版）"""
        if not raw or len(raw.strip()) < 6:
            raise ParameterError("密码长度不能少于6位")

        async with async_session_factory() as session:
            from app.api.cms.model.user_identity import UserIdentity
            result = await session.execute(select(UserIdentity).where(UserIdentity.user_id == self.id))
            user_identity = result.scalar_one_or_none()

            if user_identity:
                # 更新密码
                user_identity.credential = generate_password_hash(raw)
            else:
                # ⚠️ 先保证 self.id 已经存在
                if not self.id:
                    await session.flush()  # 🔥 立即写入 user 表并生成 ID
                user_identity = UserIdentity(
                    user_id=self.id,
                    identity_type="USERNAME_PASSWORD",
                    identifier=self.username,
                    credential=generate_password_hash(raw),
                )
                session.add(user_identity)
            await session.commit()

    async def verify_password(self, raw: str) -> bool:
        """验证密码"""
        from app.api.cms.model.user_identity import UserIdentity

        async with async_session_factory() as session:
            result = await session.execute(select(UserIdentity).where(UserIdentity.user_id == self.id))
            user_identity = result.scalar_one_or_none()
            if not user_identity:
                return False
            return check_password_hash(raw, user_identity.credential)

    # ======================================================
    # 🧠 状态判断
    # ======================================================
    @property
    def is_active(self) -> bool:
        """是否激活"""
        return not getattr(self, "is_deleted", False)

    async def is_admin(self) -> bool:
        """异步判断是否超级管理员（安全版 + 可扩展）"""
        from app.api.cms.model.user_group import UserGroup
        from app.pedro.enums import GroupLevelEnum

        async with async_session_factory() as session:
            stmt = select(UserGroup.group_id).where(UserGroup.user_id == self.id)
            result = await session.execute(stmt)
            group_ids = [gid for gid, in result.all()]  # ✅ 一次性取出所有 group_id

            # 🚀 判断是否包含 ROOT 管理员组
            return GroupLevelEnum.ROOT.value in group_ids

    # ======================================================
    # 🖼️ 头像拼接
    # ======================================================
    @property
    def avatar(self) -> Optional[str]:
        """拼接完整头像 URL"""
        settings = get_current_settings()
        domain = settings.app.oss_domain
        if not self._avatar:
            return None
        # ✅ 判断是否是第三方 URL（以 http:// 或 https:// 开头）
        if self._avatar.startswith("http://") or self._avatar.startswith("https://"):
            # 是外链（例如 Google 头像）
            return self._avatar
        else:
            return os.path.join(domain, "static", self._avatar)

    # ======================================================
    # 🔍 工具方法
    # ======================================================
    async def set_extra(self, **fields):
        """单字段/多字段写入 user.extra，自动 merge"""
        extra = self.extra or {}
        extra.update(fields)
        return await self.update(commit=True, extra=extra)

    async def update_extra(self, data: dict):
        extra = self.extra or {}
        extra.update(data)
        return await self.update(commit=True, extra=extra)

    def get_extra(self, key: str, default=None):
        return (self.extra or {}).get(key, default)

    @classmethod
    async def count_by_id(cls, uid: int) -> int:
        """根据 ID 统计数量"""
        async with async_session_factory() as session:
            result = await session.execute(
                select(func.count(cls.id)).where(cls.id == uid, cls.is_deleted == False)
            )
            return result.scalar_one()

    @classmethod
    async def verify(cls, username: str, password: str) -> "User":
        """验证用户名密码"""
        async with async_session_factory() as session:
            result = await session.execute(
                select(cls).where(cls.username == username)
            )
            user = result.scalar_one_or_none()

            if not user:
                raise NotFound("用户不存在")
            if not await user.check_password(password):
                raise ParameterError("密码错误，请输入正确密码")
            if not user.is_active:
                raise UnAuthentication("用户未激活")
            return user



class Group(AbstractGroup, BaseModel):
    __tablename__ = "group"


class Permission(AbstractPermission, BaseModel):
    __tablename__ = "permission"


class GroupPermission(AbstractGroupPermission, BaseModel):
    __tablename__ = "group_permission"


class UserGroup(AbstractUserGroup, BaseModel):
    __tablename__ = "user_group"


class UserIdentity(AbstractUserIdentity, BaseModel):
    __tablename__ = "user_identity"
