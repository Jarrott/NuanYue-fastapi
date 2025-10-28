# -*- coding: utf-8 -*-
"""
Pedro-Core 初始化核心 (init_pedro_core)
-----------------------------------------
✅ 自动加载配置（settings_manager）
✅ 异步数据库引擎初始化（SQLAlchemy 2.x）
✅ 自动扫描 model 模块并注册
✅ Manager 自动实例化并注入 FastAPI
✅ Redis / RabbitMQ / 其他拓展预留
"""

import asyncio
import importlib
import pkgutil
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config.settings_manager import get_current_settings
from app.pedro.db import BaseModel, async_session_factory
from app.pedro.manager import init_manager


# ======================================================
# 🧠 自动发现模块函数
# ======================================================
def _auto_import_models(package_name: str):
    """
    自动导入模型模块，例如 app.pedro.model.*
    """
    package = importlib.import_module(package_name)
    for _, module_name, is_pkg in pkgutil.iter_modules(package.__path__):
        if not is_pkg:
            full_name = f"{package_name}.{module_name}"
            importlib.import_module(full_name)
            print(f"🧩 已加载模型模块: {full_name}")


# ======================================================
# 🚀 Pedro-Core 初始化入口
# ======================================================
async def init_pedro_core(
    app: FastAPI,
    *,
    model_package: str = "app.pedro.model",
    with_db_init: bool = True,
    with_manager: bool = True,
    group_model=None,
    user_model=None,
    group_permission_model=None,
    permission_model=None,
    identity_model=None,
    user_group_model=None,
) -> None:
    """
    初始化 Pedro-Core 核心系统
    支持两种模式：
    ✅ 自动导入 app.pedro.model.*
    ✅ 手动传入模型类
    """

    print("🚀 Pedro-Core FastAPI 初始化中 ...")

    # ======================================================
    # Step 1. 加载配置
    # ======================================================
    settings = get_current_settings()
    app.state.settings = settings
    print(f"✅ 已加载配置环境: {settings.app.env}")

    # ======================================================
    # Step 2. 自动导入模型模块（如果未手动传入）
    # ======================================================
    if not all([group_model, user_model, permission_model]):
        print(f"🧩 自动导入模型包: {model_package}")
        _auto_import_models(model_package)
        # 自动从包中导入常见模型（兜底）
        try:
            mod = importlib.import_module(model_package)
            group_model = getattr(mod, "Group", None)
            user_model = getattr(mod, "User", None)
            permission_model = getattr(mod, "Permission", None)
            group_permission_model = getattr(mod, "GroupPermission", None)
            user_group_model = getattr(mod, "UserGroup", None)
            identity_model = getattr(mod, "UserIdentity", None)
        except Exception as e:
            print(f"⚠️ 自动加载模型包失败: {e}")

    # ======================================================
    # 🧩 Step 3. 异步数据库初始化
    # ======================================================
    if with_db_init:
        from app.pedro.db import engine  # ✅ 用 engine，而不是 async_session_factory
        print("🗃️ 正在初始化数据库表结构 ...")
        async with engine.begin() as conn:
            await conn.run_sync(BaseModel.metadata.create_all)
        print("✅ 数据库表已同步")

    # ======================================================
    # Step 4. 初始化 Manager
    # ======================================================
    if with_manager:
        manager = init_manager(
            app,
            group_model=group_model,
            user_model=user_model,
            identity_model=identity_model,
            permission_model=permission_model,
            group_permission_model=group_permission_model,
            user_group_model=user_group_model,
        )
        app.state.manager = manager
        print("✅ Pedro-Core Manager 已注册")

    # ======================================================
    # Step 5. 打印启动信息
    # ======================================================
    print("🌿 Pedro-Core 初始化完成！")
    print(f"环境: {settings.app.env} | 数据库: {settings.database.url}")

