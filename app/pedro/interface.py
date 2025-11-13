# -*- coding: utf-8 -*-
"""
Pedro-Core 接口定义层（Interface Layer）
--------------------------------------------
✅ 提供字段定义和通用方法，不注册到数据库
✅ 由 model 层继承实现实际 ORM 映射
✅ 兼容 SQLAlchemy 2.x 异步 Session
✅ 支持自定义 query、分页、计数、排序
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Type, TypeVar, Union

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    SmallInteger,
    String,
    func,
    select,
    text,
    asc,
    desc,
    BigInteger
)
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import declarative_mixin

from app.pedro.db import BaseModel, async_session_factory
from .enums import GroupLevelEnum

T = TypeVar("T", bound="BaseCrud")


# ======================================================
# 🧩 通用抽象基类
# ======================================================
class BaseCrud(BaseModel):
    """基础 CRUD 抽象类，不绑定表名"""
    __abstract__ = True

    id = Column(Integer, primary_key=True, autoincrement=True)

    # ======================================================
    # 🔍 通用查询（兼容 query / filters）
    # ======================================================
    @classmethod
    async def get(
            cls: Type[T],
            *,
            one: bool = True,
            query=None,
            order_by: str | None = None,
            sort: str = "asc",
            offset: int | None = None,
            limit: int | None = None,
            **filters: Any,
    ) -> Union[Optional[T], list[T]]:
        """
        通用查询：
        ✅ 支持 query=select(cls) 自定义查询对象
        ✅ 支持 filter_by(**filters)
        ✅ 支持排序、分页
        """
        async with async_session_factory() as session:
            # 🔸 兼容外部传入完整查询
            if query is not None:
                stmt = query
            else:
                stmt = select(cls).filter_by(**filters)

            # 🔸 排序
            if order_by and hasattr(cls, order_by):
                order_col = getattr(cls, order_by)
                stmt = stmt.order_by(
                    desc(order_col) if sort.lower() == "desc" else asc(order_col)
                )

            # 🔸 分页
            if offset is not None:
                stmt = stmt.offset(offset)
            if limit is not None:
                stmt = stmt.limit(limit)

            result = await session.execute(stmt)

            if one:
                return result.scalars().first()
            return list(result.scalars().all())

    # ======================================================
    # 📄 通用分页查询（含模糊搜索 + 排序）
    # ======================================================
    # ======================================================
    # 📄 通用分页查询（含模糊搜索 + 排序 + 布尔识别增强）
    # ======================================================
    @classmethod
    async def paginate(
            cls: Type[T],
            *,
            page: int = 1,
            size: int = 10,
            filters: Optional[dict] = None,
            keyword: Optional[str] = None,
            keyword_fields: Optional[list[str]] = None,
            order_by: Optional[str] = None,
            sort: str = "desc",
    ) -> tuple[list[T], int]:
        """
        📄 Pedro-Core 通用分页查询（安全版）
        -------------------------------------------------
        ✅ 支持 filters 等值查询（布尔/数值/字符串自动识别）
        ✅ 支持 keyword 模糊搜索（多字段）
        ✅ 支持排序与分页
        ✅ 自动统计总数，复用同样的过滤条件
        ✅ 兼容 PostgreSQL / MySQL / SQLite
        -------------------------------------------------
        返回: (items, total)
        """

        def normalize_value(v):
            """🔧 通用类型转换（布尔安全）"""
            if v is None:
                return None
            if isinstance(v, str):
                lv = v.lower().strip()
                if lv in ("1", "true", "t", "yes", "y"):
                    return True
                if lv in ("0", "false", "f", "no", "n"):
                    return False
                # 尝试转数字
                try:
                    if "." in lv:
                        return float(lv)
                    return int(lv)
                except ValueError:
                    return lv
            return v

        async with async_session_factory() as session:
            stmt = select(cls)

            # ======================================================
            # 🔹 等值过滤（布尔安全 + 兼容多数据库）
            # ======================================================
            if filters:
                for k, v in filters.items():
                    if hasattr(cls, k):
                        v = normalize_value(v)
                        if v is not None:
                            stmt = stmt.where(getattr(cls, k) == v)

            # ======================================================
            # 🔹 模糊搜索（多字段匹配）
            # ======================================================
            if keyword and keyword_fields:
                from sqlalchemy import or_
                like_pattern = f"%{keyword}%"
                stmt = stmt.where(
                    or_(
                        *[
                            getattr(cls, f).ilike(like_pattern)
                            if hasattr(cls, f) and hasattr(getattr(cls, f), "ilike")
                            else getattr(cls, f).like(like_pattern)
                            for f in keyword_fields
                            if hasattr(cls, f)
                        ]
                    )
                )

            # ======================================================
            # 🔹 排序
            # ======================================================
            if order_by and hasattr(cls, order_by):
                order_col = getattr(cls, order_by)
                stmt = stmt.order_by(
                    desc(order_col) if sort.lower() == "desc" else asc(order_col)
                )
            else:
                # 默认按主键倒序
                if hasattr(cls, "id"):
                    stmt = stmt.order_by(desc(cls.id))

            # ======================================================
            # 🔹 分页
            # ======================================================
            offset = max(page - 1, 0) * size
            stmt = stmt.offset(offset).limit(size)

            # ======================================================
            # 🔹 执行分页查询
            # ======================================================
            result = await session.execute(stmt)
            items = list(result.scalars().all())

            # ======================================================
            # 🔹 构造 count 查询（复用 where 条件）
            # ======================================================
            count_stmt = select(func.count(cls.id))
            for w in stmt._where_criteria:
                count_stmt = count_stmt.where(w)

            total = (await session.execute(count_stmt)).scalar() or 0

            return items, int(total)

    # ======================================================
    # 🔢 计数查询（支持 query / filters）
    # ======================================================
    @classmethod
    async def count(cls, query=None, **filters: Any) -> int:
        async with async_session_factory() as session:
            if query is not None:
                count_stmt = query.with_only_columns(func.count(cls.id))
            else:
                count_stmt = select(func.count(cls.id)).filter_by(**filters)
            result = await session.execute(count_stmt)
            return int(result.scalar() or 0)

    # ======================================================
    # 🆕 创建记录
    # ======================================================
    @classmethod
    async def create(cls: Type[T], commit: bool = True, **data: Any) -> T:
        async with async_session_factory() as session:
            obj = cls(**data)
            session.add(obj)
            await session.flush()
            await session.refresh(obj)
            if commit:
                await session.commit()
            return obj

    # ======================================================
    # 🔁 Upsert（存在则更新，否则创建）
    # ======================================================
    @classmethod
    async def upsert(cls: Type[T], where: dict, data: dict, commit: bool = True) -> T:
        async with async_session_factory() as session:
            stmt = select(cls).filter_by(**where).limit(1)
            result = await session.execute(stmt)
            instance = result.scalars().first()

            if instance:
                for k, v in data.items():
                    if hasattr(instance, k):
                        setattr(instance, k, v)
                session.add(instance)
            else:
                instance = cls(**{**where, **data})
                session.add(instance)

            await session.flush()
            if commit:
                await session.commit()
                await session.refresh(instance)
            return instance

    # ======================================================
    # ✏️ 更新当前实例
    # ======================================================
    async def update(self: T, commit: bool = False, **data: Any) -> T:
        async with async_session_factory() as session:
            for k, v in data.items():
                if hasattr(self, k):
                    setattr(self, k, v)
            session.add(self)
            await session.flush()
            if commit:
                await session.commit()
                await session.refresh(self)
            return self

    # ======================================================
    # ❌ 删除当前实例
    # ======================================================
    async def delete(self: T, commit: bool = False) -> None:
        async with async_session_factory() as session:
            await session.delete(self)
            if commit:
                await session.commit()

    # ======================================================
    # 🔍 通用模糊查询（多字段 ilike / like）
    # ======================================================
    @classmethod
    async def filter_like(
            cls: Type[T],
            *,
            keyword: str,
            fields: list[str],
            filters: Optional[dict] = None,
            limit: int = 20,
            sort: str = "desc",
            order_by: Optional[str] = None,
    ) -> list[T]:
        """
        🔍 多字段模糊匹配查询（非分页）
        -------------------------------------------------
        ✅ 传入关键字与字段列表，返回匹配结果
        ✅ 可同时叠加等值过滤条件
        ✅ 自动识别 PostgreSQL / SQLite 的 ilike / like
        ✅ 内部自动处理排序与 limit
        -------------------------------------------------
        用法示例：
            await ShopProduct.filter_like(
                keyword="面膜",
                fields=["title", "description", "brand"],
                limit=10
            )
        """
        from sqlalchemy import or_

        if not keyword or not fields:
            return []

        async with async_session_factory() as session:
            stmt = select(cls)

            # 🔹 等值过滤
            if filters:
                for k, v in filters.items():
                    if hasattr(cls, k) and v is not None:
                        stmt = stmt.where(getattr(cls, k) == v)

            # 🔹 多字段模糊匹配
            like_pattern = f"%{keyword}%"
            conditions = []
            for f in fields:
                if not hasattr(cls, f):
                    continue
                col = getattr(cls, f)
                if hasattr(col, "ilike"):  # PostgreSQL
                    conditions.append(col.ilike(like_pattern))
                else:  # SQLite / MySQL
                    conditions.append(col.like(like_pattern))
            if conditions:
                stmt = stmt.where(or_(*conditions))

            # 🔹 排序
            if order_by and hasattr(cls, order_by):
                order_col = getattr(cls, order_by)
                stmt = stmt.order_by(
                    desc(order_col) if sort.lower() == "desc" else asc(order_col)
                )
            elif hasattr(cls, "id"):
                stmt = stmt.order_by(desc(cls.id))

            # 🔹 限制数量
            if limit:
                stmt = stmt.limit(limit)

            result = await session.execute(stmt)
            return list(result.scalars().all())


# ======================================================
# 🕒 通用时间戳 + 软删除
# ======================================================
class InfoCrud(BaseCrud):
    __abstract__ = True

    create_time = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    update_time = Column(
        DateTime(timezone=True),
        onupdate=lambda: datetime.now(timezone.utc),
        server_onupdate=func.now(),
    )
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
    __abstract__ = True
    group_id = Column(Integer, nullable=False, comment="分组ID")
    permission_id = Column(Integer, nullable=False, comment="权限ID")


# ======================================================
# 🔑 权限接口
# ======================================================
class AbstractPermission(InfoCrud):
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


# ======================================================
# 👤 用户接口
# ======================================================
def normalize_keys(d: dict) -> dict:
    if not isinstance(d, dict):
        return d
    return {k.lower(): normalize_keys(v) for k, v in d.items()}


def default_extra() -> dict:
    from app.config.settings_manager import get_current_settings
    settings = get_current_settings()
    extra_default = getattr(settings.extra, "default", {})
    return normalize_keys(extra_default)


class AbstractUser(InfoCrud):
    __abstract__ = True

    username = Column(String(24), nullable=False, unique=True, index=True, comment="用户名")
    nickname = Column(String(24), comment="昵称")
    _avatar = Column(String(500), comment="头像URL")
    email = Column(String(100), unique=True, index=True, comment="邮箱")
    uuid = Column(BigInteger, unique=True, index=True, comment="UUID")
    register_type = Column(String(30), comment="注册类型")

    from sqlalchemy.dialects.postgresql import JSONB
    extra = Column(
        MutableDict.as_mutable(JSONB),
        default=lambda: default_extra(),
        comment="扩展字段",
    )

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
    __abstract__ = True
    user_id = Column(Integer, nullable=False, comment="用户ID")
    group_id = Column(Integer, nullable=False, comment="分组ID")


# ======================================================
# 🪪 用户身份接口
# ======================================================
class AbstractUserIdentity(InfoCrud):
    __abstract__ = True
    user_id = Column(Integer, nullable=False, comment="用户ID")
    identity_type = Column(String(100), nullable=False, comment="认证类型")
    identifier = Column(String(100), comment="标识")
    credential = Column(String(255), comment="凭证")
