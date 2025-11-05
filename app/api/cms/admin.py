# -*- coding: utf-8 -*-
"""
Pedro-Core FastAPI 用户模块 (Async Version)
---------------------------------------------
✅ 异步 SQLAlchemy ORM 操作
✅ Redis 缓存 / RabbitMQ 延迟任务
✅ JWT 登录认证
✅ 支持会员开通、签到、邀请关系树
"""
import datetime

from fastapi import APIRouter, Depends

from app.api.cms.model import User
from app.api.cms.schema.admin import AdminDepositSchema, AdminBroadcastSchema, FirebaseCreateUserSchema, KYCReviewSchema
from app.api.cms.services.deposit_approve_service import DepositApproveService
from app.api.cms.services.firebase_admin_service import FirebaseAdminService
from app.api.v1.schema.response import SuccessResponse
from app.extension.google_tools.firestore import fs_service
from app.extension.redis.redis_client import rds
from app.extension.websocket.tasks.ws_user_notify import notify_user, notify_broadcast
from app.extension.websocket.wss import websocket_manager

from app.config.settings_manager import get_current_settings
from app.pedro.enums import KYCStatus
from app.pedro.pedro_jwt import admin_required, jwt_service
from app.pedro.response import PedroResponse

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


@rp.post("/create-user")
async def create_firebase_user(data: FirebaseCreateUserSchema):
    try:
        # 创建 Firebase 用户
        user = FirebaseAdminService.create_user(
            email=data.email,
            password=data.password,
            display_name=data.display_name or data.email.split("@")[0],
        )

        # 赋予管理员权限
        if data.admin:
            FirebaseAdminService.set_admin(user.uid, True)

        return {
            "message": "User created successfully",
            "uid": user.uid,
            "email": user.email,
            "admin": data.admin,
        }

    except Exception as e:
        raise e


@rp.put("/kyc/review", name="审核KYC内容")
async def review_kyc(data: KYCReviewSchema, admin = Depends(admin_required)):
    uid = data.user_id

    # ✅ Firestore 更新审核记录
    await fs_service.update(
        path=f"users/{uid}/kyc/info",
        data={
            "status": "approved" if data.approve else "rejected",
            "review_by": admin.id,
            "review_reason": data.reason or "",
        }
    )

    # ✅ 更新 PGSQL 用户扩展字段
    user = await User.get(id=uid)
    new_status = KYCStatus.APPROVED.value if data.approve else KYCStatus.REJECTED.value
    await user.set_extra(kyc_status=new_status)

    return PedroResponse.success(
        msg=f"KYC审核{'通过' if data.approve else '拒绝'}"
    )
