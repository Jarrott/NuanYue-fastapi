"""
Pedro-Core Manager (FastAPI版)
--------------------------------
重构自 LinCMS 的 Manager 模块，支持异步ORM与FastAPI依赖注入。

✅ 异步查询与权限同步
✅ 自动挂载到 app.state.manager
✅ 保留 meta / plugin / model / services 管理接口
✅ 支持权限检查 (is_user_allowed)
"""

import asyncio
from typing import Any, Dict, List, Optional, Type, Union
from fastapi import FastAPI, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.pedro.loader import Loader  # 可复用原Lin Loader逻辑
from app.pedro.exception import AuthFailed, NotFound
from app.pedro.model import (User, UserGroup,Group,
                             UserIdentity, Permission,
                             GroupPermission)


class Manager:
    """Pedro-Core 权限与资源管理器"""

    ep_meta: Dict[str, Any] = {}

    def __init__(
            self,
            plugin_path: Optional[Dict[str, Any]] = None,
            group_model: Optional[Type[Any]] = None,
            user_model: Optional[Type[Any]] = None,
            identity_model: Optional[Type[Any]] = None,
            permission_model: Optional[Type[Any]] = None,
            group_permission_model: Optional[Type[Any]] = None,
            user_group_model: Optional[Type[Any]] = None,
    ):
        self.plugin_path = plugin_path or {}
        self.group_model = Group
        self.user_model = User
        self.identity_model = UserIdentity
        self.permission_model = Permission
        self.group_permission_model = GroupPermission
        self.user_group_model = UserGroup

        self.loader: Loader = Loader(self.plugin_path)
        print("✅ Pedro-Core Manager 已初始化")

    # -------------------------------------------------------
    # 🧩 用户 & 分组操作
    # -------------------------------------------------------

    async def find_user(self, session: AsyncSession, **kwargs) -> Optional[Any]:
        stmt = select(self.user_model).filter_by(**kwargs)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_group(self, session: AsyncSession, **kwargs) -> Optional[Any]:
        stmt = select(self.group_model).filter_by(**kwargs)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_user_group(self, session: AsyncSession, user_id: int):
        stmt = select(
            self.user_group_model.id,
            self.user_group_model.user_id,
            self.user_group_model.group_id
        ).where(self.user_group_model.user_id == user_id)

        # ✅ 打印完整 SQL（带绑定值）
        print("[DEBUG SQL]", stmt.compile(compile_kwargs={"literal_binds": True}))

        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def verify_user(self, session: AsyncSession, username: str, password: str) -> Optional[Any]:
        user = await self.find_user(session, username=username)
        if not user or user.password != password:
            raise AuthFailed("用户名或密码错误")
        return user

    # -------------------------------------------------------
    # 🧠 权限同步与查询
    # -------------------------------------------------------
    async def get_ep_infos(self, session: AsyncSession) -> Dict[str, List[Any]]:
        stmt = select(self.permission_model).filter_by(mount=True)
        result = await session.execute(stmt)
        infos = {}
        for perm in result.scalars().all():
            infos.setdefault(perm.module, []).append(perm)
        return infos

    def find_info_by_ep(self, ep: str) -> Optional[Any]:
        info = self.ep_meta.get(ep)
        return info if info and getattr(info, "mount", True) else None

    async def find_group_ids_by_user_id(self, session: AsyncSession, user_id: int) -> List[int]:
        UG, U, G = self.user_group_model, self.user_model, self.group_model

        subq = select(UG.group_id).join(U, U.id == UG.user_id).where(
            U.is_deleted == False, U.id == user_id
        )
        result = await session.execute(select(G.id).where(G.id.in_(subq)))
        return [x[0] for x in result.all()]

    async def is_user_allowed(self, session: AsyncSession, user_id: int, request: Request) -> bool:
        ep = request.scope.get("endpoint")
        if not ep:
            return False
        meta = self.ep_meta.get(ep)
        if not meta:
            return False

        group_ids = await self.find_group_ids_by_user_id(session, user_id)
        GP, P = self.group_permission_model, self.permission_model

        subq = select(GP.permission_id).where(GP.group_id.in_(group_ids))
        stmt = (
            select(P)
            .filter_by(module=meta.module, name=meta.name, mount=True)
            .where(P.id.in_(subq))
        )
        result = await session.execute(stmt)
        return bool(result.scalar_one_or_none())

    # -------------------------------------------------------
    # 🧩 插件 / 模型 / 服务注册
    # -------------------------------------------------------
    @property
    def plugins(self) -> Dict[str, Any]:
        return self.loader.plugins

    def get_plugin(self, name: str) -> Optional[Any]:
        return self.loader.plugins.get(name)

    def get_model(self, name: str) -> Optional[Any]:
        for plugin in self.plugins.values():
            model = plugin.models.get(name)
            if model:
                return model
        return None

    def get_service(self, name: str) -> Optional[Any]:
        for plugin in self.plugins.values():
            service = plugin.services.get(name)
            if service:
                return service
        return None


# =======================================================
# 🔧 Manager 实例注册与 FastAPI 兼容接口
# =======================================================
_manager_instance: Optional[Manager] = None


def init_manager(app: FastAPI, **models) -> Manager:
    global _manager_instance
    _manager_instance = Manager(**models)
    app.state.manager = _manager_instance
    print("✅ Manager 已注册到 FastAPI state")
    return _manager_instance


def get_manager(request: Request) -> Manager:
    manager = getattr(request.app.state, "manager", None)
    if not manager:
        raise RuntimeError("Manager 未初始化，请在 app 初始化时调用 init_manager()")
    return manager


manager = Manager()
