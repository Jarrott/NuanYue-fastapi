# -*- coding: utf-8 -*-
"""
Pedro-Core FastAPI 用户模块 (Async Version)
---------------------------------------------
✅ 异步 SQLAlchemy ORM 操作
✅ Redis 缓存 / RabbitMQ 延迟任务
✅ JWT 登录认证
✅ 支持会员开通、签到、邀请关系树
"""

from fastapi import APIRouter, Depends
from app.api.v1.handler.response import SuccessResponse, LoginSuccessResponse
from app.extension.websocket.wss import websocket_manager

from app.config.settings_manager import get_current_settings
from app.pedro.pedro_jwt import admin_required, jwt_service

rp = APIRouter(prefix="/admin", tags=["用户"])
settings = get_current_settings()


@rp.get("/push/message", response_model=SuccessResponse,
        dependencies=[Depends(admin_required)])
async def broadcast_system_announcement():
    await websocket_manager.broadcast_all("🚨 系统将在 10 分钟后进行维护，请及时保存工作。")
    return SuccessResponse(msg="信息已成功推送")

@rp.post("/force_logout/{uid}")
async def force_logout(uid: int):
    logout = await jwt_service.bump_version(uid)
    if not logout:
        return SuccessResponse(msg="没有成功")
    return SuccessResponse(msg="已强制踢出")