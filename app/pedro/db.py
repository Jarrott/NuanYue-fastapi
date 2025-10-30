# -*- coding: utf-8 -*-
"""
Pedro-Core 异步 ORM 基类 (Final Unified Version)
---------------------------------------------
✅ 异步 CRUD 接口
✅ auto_commit() 自动事务上下文
✅ soft_delete / hard_delete
✅ filter_by(soft=True)
✅ get_or_404 / first_or_404
✅ hide() / to_dict() 智能序列化
✅ count() / exists() / query()
✅ 内置异步 engine / session_factory
✅ 兼容 FastAPI 生命周期
"""

from __future__ import annotations
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Optional, List, Dict, Type, TypeVar, AsyncGenerator
from sqlalchemy import Column, Integer, Boolean, DateTime, select, func
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.orm import declarative_base, declared_attr
from fastapi import HTTPException, status
from contextlib import asynccontextmanager
import json

# ======================================================
# ⚙️ ORM Base 定义
# ======================================================
Base = declarative_base()
T = TypeVar("T", bound="BaseModel")


# ======================================================
# ⚙️ Pedro-Core ORM BaseModel
# ======================================================
class BaseModel(Base):
    __abstract__ = True

    id = Column(Integer, primary_key=True, autoincrement=True)
    is_deleted = Column(Boolean, default=False, nullable=False)

    # -----------------------------------------
    # 🧩 自动表名
    # -----------------------------------------
    @declared_attr.directive
    def __tablename__(cls) -> str:
        """驼峰转下划线"""
        name = cls.__name__
        return "".join(["_" + i.lower() if i.isupper() else i for i in name]).lstrip("_")

    # -----------------------------------------
    # 🧱 字段过滤 & 序列化
    # -----------------------------------------
    def hide(self, *args: str) -> "BaseModel":
        if not hasattr(self, "_hidden_fields"):
            self._hidden_fields = []
        self._hidden_fields.extend(args)
        return self

    def to_dict(self, exclude: Optional[List[str]] = None) -> Dict[str, Any]:
        exclude = exclude or []
        hidden = getattr(self, "_hidden_fields", [])
        exclude = set(exclude + hidden)

        def _convert(value: Any):
            if isinstance(value, datetime):
                return value.isoformat()
            if isinstance(value, (dict, list)):
                return value
            try:
                json.dumps(value)
                return value
            except Exception:
                return str(value)

        return {
            k: _convert(v)
            for k, v in self.__dict__.items()
            if not k.startswith("_") and k not in exclude
        }

    # -----------------------------------------
    # 🔍 通用异步 CRUD 操作
    # -----------------------------------------
    @classmethod
    async def get(cls: Type[T], session: AsyncSession, id: int) -> Optional[T]:
        stmt = select(cls).where(cls.id == id, cls.is_deleted.is_(False))
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @classmethod
    async def get_or_404(cls: Type[T], session: AsyncSession, id: int) -> T:
        instance = await cls.get(session, id)
        if not instance:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{cls.__name__} 不存在")
        return instance

    @classmethod
    async def first_or_404(cls: Type[T], session: AsyncSession, **filters) -> T:
        stmt = select(cls).filter_by(**filters)
        result = await session.execute(stmt)
        instance = result.scalar_one_or_none()
        if not instance:
            raise HTTPException(status_code=404, detail=f"{cls.__name__} 未找到")
        return instance

    @classmethod
    async def filter_by(
            cls: Type[T],
            session: AsyncSession,
            soft: bool = False,
            **filters,
    ) -> List[T]:
        stmt = select(cls).filter_by(**filters)
        if soft:
            stmt = stmt.where(cls.is_deleted.is_(False))
        result = await session.execute(stmt)
        return result.scalars().all()

    @classmethod
    async def count(cls: Type[T], session: AsyncSession, soft: bool = True) -> int:
        stmt = select(func.count(cls.id))
        if soft:
            stmt = stmt.where(cls.is_deleted.is_(False))
        result = await session.execute(stmt)
        return result.scalar() or 0

    @classmethod
    async def exists(cls: Type[T], session: AsyncSession, **filters) -> bool:
        stmt = select(func.count(cls.id)).filter_by(**filters)
        result = await session.execute(stmt)
        return (result.scalar() or 0) > 0

    # -----------------------------------------
    # ✏️ 写入、更新、删除
    # -----------------------------------------
    @classmethod
    async def create(cls: Type[T], session: AsyncSession, **data) -> T:
        obj = cls(**data)
        session.add(obj)
        await session.commit()
        await session.refresh(obj)
        return obj

    async def update(self, session: AsyncSession, **kwargs) -> T:
        for k, v in kwargs.items():
            setattr(self, k, v)
        await session.commit()
        await session.refresh(self)
        return self

    async def delete(self, session: AsyncSession):
        """硬删除"""
        await session.delete(self)
        await session.commit()

    async def soft_delete(self, session: AsyncSession):
        """软删除"""
        self.is_deleted = True
        await session.commit()
        await session.refresh(self)

    # -----------------------------------------
    # 🔁 通用查询入口
    # -----------------------------------------
    @classmethod
    def query(cls, session: AsyncSession):
        return session.execute(select(cls).where(cls.is_deleted == False))

    # -----------------------------------------
    # 🔒 自动事务上下文
    # -----------------------------------------
    @classmethod
    @asynccontextmanager
    async def auto_commit(cls, session: AsyncSession):
        try:
            yield
            await session.commit()
        except Exception as e:
            await session.rollback()
            raise e


# ======================================================
# ⚙️ 异步引擎 & Session 工厂
# ======================================================

# ✅ 自动适配异步数据库URL (sqlite / postgres / mysql)
@lru_cache()
def get_engine():
    """
    延迟初始化数据库引擎
    避免 settings_manager ↔ pedro 循环导入
    """
    import importlib
    settings_manager = importlib.import_module("app.config.settings_manager")
    settings = settings_manager.get_current_settings()
    return create_async_engine(
        settings.database.url,
        echo=False,
        future=True,
    )

@lru_cache()
def get_session_factory():
    engine = get_engine()
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

# ✅ 提供简洁别名（兼容旧代码）
engine = get_engine()
async_session_factory = get_session_factory()

# ======================================================
# 🧩 全局 Session 依赖函数（FastAPI 可直接使用）
# ======================================================
@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：异步数据库会话"""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
