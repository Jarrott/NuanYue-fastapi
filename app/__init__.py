# -*- coding: utf-8 -*-
"""
FastAPI 应用初始化入口 (Pedro-Core 适配版)
--------------------------------------------
兼容原 Flask 架构的注册逻辑：
✅ 模块自动注册 (蓝图)
✅ Redis / MQ / SocketIO 初始化
✅ 日志 / CORS / 异常 / 配置加载
✅ Pedro-Core 初始化（数据库 + 权限模型）
"""

import os
from dotenv import load_dotenv
from fastapi import FastAPI

from app.config.settings_manager import get_current_settings
from app.pedro.syslogger import setup_logger

# ======================================================
# 🧩 环境初始化
# ======================================================
basedir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(basedir, ".env")
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    print(f"⚠️ 未找到 {env_path}")

logger = setup_logger("pedro_core")


# ======================================================
# 🧱 注册模块与服务
# ======================================================
def register_blueprints(app: FastAPI):
    """注册 API 模块（原 Flask 蓝图）"""
    from app.api import create_v1
    router_v1 = create_v1()
    app.include_router(router_v1)
    logger.info("✅ 已注册 API 模块: v1")


def register_cors(app: FastAPI):
    """注册 CORS 中间件"""
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.info("✅ CORS 中间件已启用")


def register_exception_handlers(app: FastAPI):
    """注册全局异常"""
    from app.pedro.exception import register_exception_handlers
    register_exception_handlers(app)
    logger.info("✅ 异常处理器已注册")


def register_logger(app: FastAPI):
    """统一日志系统"""
    from app.pedro.logger import setup_logger
    setup_logger(app)
    logger.info("✅ 日志系统初始化完成")


def register_service_extensions(app: FastAPI):
    """注册 Redis / RabbitMQ 等外部服务"""
    from app.pedro.service_manager import service

    @app.on_event("startup")
    async def startup_service():
        await service.init_all()
        logger.info("✅ 异步服务模块启动完成")

    @app.on_event("shutdown")
    async def shutdown_service():
        await service.close_all()
        logger.info("🧹 异步服务模块已关闭")


def register_pedro_core(app: FastAPI):
    """Pedro-Core 初始化（数据库 + 权限模型 + Manager）"""
    from app.pedro.pedro import init_pedro_core
    from app.api.cms.model import (
        User, Group, UserGroup,
        UserIdentity, GroupPermission, Permission
    )

    @app.on_event("startup")
    async def startup_core():
        await init_pedro_core(
            app=app,
            group_model=Group,
            user_model=User,
            group_permission_model=GroupPermission,
            permission_model=Permission,
            identity_model=UserIdentity,
            user_group_model=UserGroup
        )
        logger.info("🌿 Pedro-Core 已初始化完成")


# ======================================================
# 🏗️ 应用工厂
# ======================================================
def create_app() -> FastAPI:
    """构建 FastAPI 实例并注册所有依赖"""
    settings = get_current_settings()

    app = FastAPI(
        title=settings.app.name,
        version=settings.app.version,
        description="Pedro CMS built on FastAPI",
        debug=settings.app.debug
    )

    # 注册所有模块
    register_logger(app)
    register_blueprints(app)
    register_cors(app)
    register_exception_handlers(app)
    register_service_extensions(app)
    register_pedro_core(app)

    logger.info(f"🚀 Pedro-Core FastAPI 初始化完成 | 环境: {settings.app.env}")
    return app
