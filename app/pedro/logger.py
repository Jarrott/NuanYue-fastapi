"""
Pedro-Core 日志系统模块
---------------------
支持：
✅ 控制台彩色日志
✅ 按天分割文件日志
✅ FastAPI 请求耗时中间件
✅ 统一异常日志捕获
✅ 自动随 settings.DEBUG 切换日志级别
"""

import sys
import time
import logging
from loguru import logger
from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.config.settings_manager import get_current_settings

settings = get_current_settings()


# ==========================
# 🧩 日志基础配置
# ==========================

LOG_PATH = "logs/app_{time:YYYY-MM-DD}.log"
LOG_LEVEL = "DEBUG" if settings.app.debug else "INFO"


def init_logger():
    """
    初始化 Loguru 日志系统
    """
    logger.remove()  # 移除默认配置
    logger.add(
        sys.stdout,
        level=LOG_LEVEL,
        enqueue=True,
        backtrace=True,
        colorize=True,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
               "<level>{message}</level>",
    )
    logger.add(
        LOG_PATH,
        rotation="00:00",      # 每天一个文件
        retention="14 days",   # 日志保留 14 天
        level=LOG_LEVEL,
        enqueue=True,
        backtrace=True,
    )
    logging.getLogger("uvicorn.access").handlers = [InterceptHandler()]
    logging.getLogger("uvicorn.error").handlers = [InterceptHandler()]
    logger.info(f"✅ Logger initialized (level={LOG_LEVEL})")


class InterceptHandler(logging.Handler):
    """将标准 logging 转发给 Loguru"""
    def emit(self, record):
        try:
            level = logger.level(record.levelname).name
        except Exception:
            level = "INFO"
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


# ==========================
# 🌐 请求日志中间件
# ==========================
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = (time.time() - start_time) * 1000
        logger.info(
            f"{request.method} {request.url.path} "
            f"status={response.status_code} "
            f"duration={process_time:.2f}ms "
            f"client={request.client.host}"
        )
        return response


# ==========================
# 🚀 初始化函数（在 main.py1 中调用）
# ==========================
def setup_logger(app: FastAPI):
    """
    在 FastAPI 应用中注册日志系统
    """
    init_logger()
    app.add_middleware(RequestLoggingMiddleware)
    logger.info("🧩 Log middleware registered successfully.")
    return logger