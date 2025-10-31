# -*- coding: utf-8 -*-
"""
FastAPI 应用初始化入口 (Pedro-Core 适配版)
--------------------------------------------
✅ lifespan 模式 (替代 on_event)
✅ 模块自动注册 (蓝图)
✅ Redis / MQ / SocketIO 初始化
✅ 日志 / CORS / 异常 / 配置加载
✅ Pedro-Core 初始化（数据库 + 权限模型）
✅ Binance 实时行情监听后台任务
"""
import asyncio
import os
from contextlib import asynccontextmanager
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
    from app.api import create_v1, create_cms

    router_v1 = create_v1()
    router_cms = create_cms()
    app.include_router(router_v1)
    app.include_router(router_cms)
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

def init_firebase():
    from app.extension.google_tools.firebase_admin_service import init_firebase_admin
    init_firebase_admin()


def register_pedro_core():
    """Pedro-Core 初始化（数据库 + 权限模型 + Manager）"""
    from app.pedro.pedro import init_pedro_core
    from app.api.cms.model import (
        User, Group, UserGroup,
        UserIdentity, GroupPermission, Permission
    )
    async def startup_core(app):
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
    return startup_core


async def init_service_modules():
    """注册 Redis / MQ / 等外部服务"""
    from app.pedro.service_manager import service

    logger.info("🪄 正在初始化外部服务 (Redis / MQ / EventBus / WebSocket)...")

    # 并发启动所有 BaseService.init()
    await service.init_all()

    logger.info("✅ 异步服务模块启动完成")

    async def cleanup():
        await service.close_all()
        logger.info("🧹 异步服务模块已关闭")

    return cleanup



async def init_binance_stream_tasks():
    """启动 Binance 实时行情监听"""
    from app.extension.stream.binance import start_realtime_market
    await start_realtime_market()
    logger.info("📡 Binance 实时行情监听已启动")


# ======================================================
# 🧬 lifespan 生命周期管理器
# ======================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """统一管理 startup / shutdown"""

    # ---- startup 阶段 ----
    logger.info("🚀 FastAPI 启动中，正在初始化模块...")

    # 1️⃣ 初始化所有扩展服务（包括 Redis/MQ/EventBusService）
    await init_service_modules()

    # 2️⃣ 注册 Pedro Core（JWT、中间件、异常、蓝图）
    await register_pedro_core()(app)

    # 3️⃣ 初始化异步任务流（例如 Binance Stream）
    asyncio.create_task(init_binance_stream_tasks())  # ✅ Binance

    logger.info("✅ 所有模块初始化完成，系统启动成功。")

    yield

    # ---- shutdown 阶段 ----
    logger.info("🧹 FastAPI 正在关闭中，清理资源...")


# ======================================================
# 🏗️ 应用工厂
# ======================================================
def create_app() -> FastAPI:
    """构建 FastAPI 实例并注册所有依赖"""
    settings = get_current_settings()
    # ✅ 根据环境动态关闭 Swagger
    docs_url = "/docs" if settings.app.debug else None
    redoc_url = "/redoc" if settings.app.debug else None
    openapi_url = "/openapi.json" if settings.app.debug else None

    app = FastAPI(
        # 生产环境不暴露API
        docs_url=docs_url,
        redoc_url=redoc_url,
        openapi_url=openapi_url,
        title=settings.app.name,
        version=settings.app.version,
        description="Pedro CMS built on FastAPI",
        debug=settings.app.debug,
        lifespan=lifespan,   # ✅ 新增：lifespan 生命周期控制
    )

    # 注册模块和中间件
    register_cors(app)
    register_logger(app)
    register_blueprints(app)
    register_exception_handlers(app)
    init_firebase()

    logger.info(f"✅ Pedro-Core FastAPI 初始化完成 | 环境: {settings.app.env}")
    return app
