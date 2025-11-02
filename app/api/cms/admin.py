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

from app.api.cms.schema.admin import AdminDepositSchema, AdminBroadcastSchema
from app.api.cms.services.deposit_approve_service import DepositApproveService
from app.api.v1.schema.response import SuccessResponse
from app.extension.redis.redis_client import rds
from app.extension.websocket.tasks.ws_user_notify import notify_user, notify_broadcast
from app.extension.websocket.wss import websocket_manager

from app.config.settings_manager import get_current_settings
from app.pedro.pedro_jwt import admin_required, jwt_service

rp = APIRouter(prefix="/admin", tags=["用户"])
settings = get_current_settings()


@rp.post("/push/message", response_model=SuccessResponse,
         dependencies=[Depends(admin_required)])
async def broadcast_system_announcement(msg: AdminBroadcastSchema):
    # 全局广播参数
    await notify_broadcast(
        {"msg": f"{msg}"}
    )
    return SuccessResponse.success(msg="信息已成功推送")


@rp.post("/push/message/{uid}", response_model=SuccessResponse,
         dependencies=[Depends(admin_required)])
async def broadcast_user_message(uid: int):
    await notify_user(uid, {
        "event": "order_created",
        "order_id": 9876,
        "msg": "订单创建成功 ✅"
    })

    return SuccessResponse.success(msg="信息已成功推送")


@rp.post("/force_logout/{uid}")
async def force_logout(uid: int):
    logout = await jwt_service.bump_version(uid)
    if not logout:
        return SuccessResponse(msg="没有成功")
    return SuccessResponse(msg="已强制踢出")


@rp.post("/approve/deposit", response_model=SuccessResponse)
async def admin_deposit(payload: AdminDepositSchema, admin=Depends(admin_required)):
    await DepositApproveService.admin_deposit(
        user_id=payload.user_id,
        amount=payload.amount,
        remark="订单审核通过",
        admin_user=admin,
        order_no=payload.order_no
    )

    await notify_user(payload.user_id, {
        "event": "wallet_recharge_success",
        "amount": payload.amount,
        "msg": f"充值成功：${payload.amount}"
    })

    return SuccessResponse(msg="管理员充值成功")


@rp.get("/ws/online/count")
async def get_ws_online_count() -> int:
    r = await rds.instance()
    return await r.scard("ws:online:uids")


@rp.get("/ws/online/detail/{uid}")
async def get_ws_online_detail(uid: int) -> dict:
    r = await rds.instance()
    return await r.hgetall(f"ws:online:detail:{uid}")


@rp.post("/binance/switch/{state}")
async def switch_market(state: int):
    """ state: 1 开启 | 0 关闭 币安数据推送ws"""
    r = await rds.instance()
    await r.set("binance:push:enabled", str(state))
    return {"status": "ok", "enabled": state}
