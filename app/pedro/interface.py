# -*- coding: utf-8 -*-
"""
Pedro-Core 接口定义层（Interface Layer）
--------------------------------------------
✅ 提供字段定义和通用方法，不注册到数据库
✅ 由 model 层继承实现实际 ORM 映射
✅ 兼容 SQLAlchemy 2.x 异步 Session
"""

from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List, Optional, Type, TypeVar, Union

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    SmallInteger,
    String,
    func,
    text,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import declarative_mixin

from app.pedro.db import BaseModel
from .enums import GroupLevelEnum


T = TypeVar("T", bound="BaseCrud")


# ======================================================
# 🧩 通用抽象基类
# ======================================================
class BaseCrud(BaseModel):
    """基础 CRUD 抽象类，不绑定表名"""
    __abstract__ = True

    id = Column(Integer, primary_key=True, autoincrement=True)

    # -------- 通用查询 --------
    @classmethod
    async def get(
        cls: Type[T],
        session: AsyncSession,
        *,
        one: bool = True,
        **filters: Any,
    ) -> Union[Optional[T], List[T]]:
        stmt = cls.select().filter_by(**filters)
        if one:
            result = await session.execute(stmt.limit(1))
            return result.scalar_one_or_none()
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    async def count(cls, session: AsyncSession, **filters: Any) -> int:
        stmt = cls.select(func.count(cls.id)).filter_by(**filters)
        result = await session.execute(stmt)
        return int(result.scalar() or 0)

    async def update(self: T, session: AsyncSession, **data: Any) -> T:
        for k, v in data.items():
            if hasattr(self, k):
                setattr(self, k, v)
        session.add(self)
        await session.flush()
        return self

    async def delete(self: T, session: AsyncSession) -> None:
        await session.delete(self)


# ======================================================
# 🕒 通用时间戳 + 软删除
# ======================================================
class InfoCrud(BaseCrud):
    """带 create/update/delete_time 的抽象类"""
    __abstract__ = True

    create_time = Column(DateTime(timezone=True), server_default=func.now())
    update_time = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())
    delete_time = Column(DateTime(timezone=True))
    is_deleted = Column(Boolean, nullable=False, default=False)

    async def soft_delete(self, session: AsyncSession) -> None:
        self.is_deleted = True
        self.delete_time = datetime.utcnow()
        session.add(self)
        await session.flush()


# ======================================================
# 👥 分组接口
# ======================================================
class AbstractGroup(InfoCrud):
    """分组字段定义"""
    __abstract__ = True

    name = Column(String(60), nullable=False, comment="分组名称")
    info = Column(String(255), comment="分组说明")
    level = Column(
        SmallInteger(),
        nullable=False,
        server_default=text(str(GroupLevelEnum.USER.value)),
        comment="分组级别 1：ROOT 2：GUEST 3：USER",
    )


# ======================================================
# 🔗 分组-权限关联接口
# ======================================================
class AbstractGroupPermission(BaseCrud):
    """分组权限关联"""
    __abstract__ = True

    group_id = Column(Integer, nullable=False, comment="分组ID")
    permission_id = Column(Integer, nullable=False, comment="权限ID")


# ======================================================
# 🔑 权限接口
# ======================================================
class AbstractPermission(InfoCrud):
    """权限字段定义"""
    __abstract__ = True

    name = Column(String(60), nullable=False, comment="权限名称")
    module = Column(String(50), nullable=False, comment="所属模块")
    mount = Column(Boolean, nullable=False, default=True, comment="是否挂载")

    def __hash__(self) -> int:
        return hash(f"{self.name}:{self.module}")

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, AbstractPermission)
            and self.name == other.name
            and self.module == other.module
        )

def normalize_keys(d: dict) -> dict:
    """递归地将所有 dict key 转为小写"""
    if not isinstance(d, dict):
        return d
    return {k.lower(): normalize_keys(v) for k, v in d.items()}

def default_extra() -> dict:
    """返回标准化的 extra 默认结构"""
    from app.config.settings_manager import get_current_settings
    settings = get_current_settings()
    extra_default = getattr(settings.extra, "default", {})
    return normalize_keys(extra_default)

# ======================================================
# 👤 用户接口
# ======================================================
class AbstractUser(InfoCrud):
    """用户基础字段定义"""
    __abstract__ = True

    username = Column(String(24), nullable=False, comment="用户名")
    nickname = Column(String(24), comment="昵称")
    avatar = Column(String(500), comment="头像URL")
    email = Column(String(100), comment="邮箱")
    from sqlalchemy.dialects.postgresql import JSONB
    extra = Column(MutableDict.as_mutable(JSONB), default=lambda :default_extra(), comment="扩展字段")

    async def verify(self, raw: str) -> bool:
        pass

    async def check_password(self, raw: str) -> bool:
        raise NotImplementedError

    @property
    def is_admin(self) -> bool:
        raise NotImplementedError


# ======================================================
# 🔗 用户-分组接口
# ======================================================
class AbstractUserGroup(BaseCrud):
    """用户-分组关联"""
    __abstract__ = True

    user_id = Column(Integer, nullable=False, comment="用户ID")
    group_id = Column(Integer, nullable=False, comment="分组ID")


# ======================================================
# 🪪 用户身份接口
# ======================================================
class AbstractUserIdentity(InfoCrud):
    """用户认证信息"""
    __abstract__ = True

    user_id = Column(Integer, nullable=False, comment="用户ID")
    identity_type = Column(String(100), nullable=False, comment="认证类型")
    identifier = Column(String(100), comment="标识")
    credential = Column(String(255), comment="凭证")
