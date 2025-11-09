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
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.params import Query

from app.api.cms.model import User
from app.api.cms.schema.admin import (
    AdminDepositSchema,
    AdminBroadcastSchema,
    FirebaseCreateUserSchema,
    KYCReviewSchema,
    ManualCreditSchema,
    MockCreateOrderSchema)

from app.api.cms.services.admin_ledger_service import AdminLedgerService
from app.api.cms.services.firebase_admin_service import FirebaseAdminService
from app.api.cms.services.orders.mock_order_service import MockOrderService
from app.api.cms.services.user_wallet_service import AdminWalletService
from app.api.v1.schema.response import SuccessResponse
from app.api.cms.services.wallet.wallet_secure_service import WalletSecureService
from app.api.cms.services.wallet.wallet_sync_service import WalletSyncService
from app.extension.google_tools.firestore import fs_service
from app.extension.redis.redis_client import rds
from app.extension.websocket.tasks.ws_user_notify import notify_user, notify_broadcast

from app.config.settings_manager import get_current_settings
from app.pedro.enums import KYCStatus
from app.pedro.pedro_jwt import admin_required, jwt_service
from app.pedro.response import PedroResponse

rp = APIRouter(prefix="/admin", tags=["管理员"])
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


@rp.post("/force_logout/{uid}", name="踢出违规用户")
async def force_logout(uid: int, admin=Depends(admin_required)):
    logout = await jwt_service.bump_version(uid)
    if not logout:
        return SuccessResponse.fail(msg="没有成功")
    return SuccessResponse.success(msg="已强制踢出")


@rp.post("/manual/credit", name="后台手动（入账）", dependencies=[Depends(admin_required)])
async def manual_credit(data: ManualCreditSchema, admin=Depends(admin_required)):
    # 管理员手动充值
    result = await AdminWalletService.manual_credit(
        uid=data.user_id,
        amount=data.amount,
        reason="活动奖励",
        admin_user="root",
        l_type="credit",
    )
    return result


@rp.post("/approve/deposit", name="管理员审核充值", response_model=PedroResponse)
async def admin_deposit(payload: AdminDepositSchema, admin=Depends(admin_required)):
    """
    ✅ 后台审核充值通过后入账
    - Firestore 原子入账
    - Ledger 可追溯
    - PostgreSQL 同步
    - RTDB 实时余额更新
    - 通知用户
    """

    reference = f"deposit:{payload.order_no}"

    uid = str(payload.user_id)

    # 1️⃣ 安全入账
    result = await WalletSecureService.credit_wallet_admin(
        uid=uid,
        amount=payload.amount,
        operator_id=admin.username,  # ✅ 正确字段名
        reference=reference,
        type="deposit_approve",  # ✅ 可传入操作类型（如充值审核通过）
        remark="充值审核通过",  # ✅ 可作为 Ledger 备注
    )

    # 2️⃣ Firestore 入账完成后，异步同步 RTDB（保险起见再同步一次）
    if result and isinstance(result, dict) and result.get("status") == "ok":
        balance_after = result.get("balance_after")
        # 异步同步，不阻塞主线程
        import asyncio
        asyncio.create_task(WalletSyncService.sync_balance(payload.user_id, balance_after))

    # 3️⃣ 发送 WebSocket 通知给用户（充值成功）
    await notify_user(payload.user_id, {
        "event": "wallet_recharge_success",
        "amount": payload.amount,
        "msg": f"充值成功：${payload.amount}"
    })

    return PedroResponse.success(
        msg=f"充值成功：${payload.amount} USD 已入账",
        # data=result
    )


@rp.post("/wallet/manual-debit", name="管理员手动（扣款）")
async def manual_debit(payload: ManualCreditSchema, admin=Depends(admin_required)):
    """
    管理员手动下分接口
    """
    # 管理员手动扣款
    res = await AdminWalletService.manual_debit(
        uid=payload.user_id,
        amount=payload.amount,
        reason="违规行为处罚" if payload.reason is None else payload.reason,
        admin_user="root",
    )
    return PedroResponse.success(msg="扣款成功")


@rp.get("/ledger/list", name="平台出入账列表（按 ledger 聚合）")
async def list_ledger(
        limit: int = Query(50, ge=1, le=200),
        page_token: Optional[str] = None,
        uid: Optional[str] = None,
        l_type: Optional[str] = Query(None, description="income/debit/withdraw/fee..."),
        start: Optional[str] = Query(None, description="ISO8601，例如 2025-11-07T00:00:00Z"),
        end: Optional[str] = Query(None, description="ISO8601"),
        reference_prefix: Optional[str] = None,
        _=Depends(admin_required),
):
    dt_start = datetime.datetime.fromisoformat(start.replace("Z", "+00:00")) if start else None
    dt_end = datetime.datetime.fromisoformat(end.replace("Z", "+00:00")) if end else None

    rows, next_token = AdminLedgerService.list_platform_ledger(
        limit=limit,
        page_token=page_token,
        uid=uid,
        l_type=l_type,
        start=dt_start,
        end=dt_end,
        reference_prefix=reference_prefix,
    )
    return PedroResponse.success(data={
        "items": rows,
        "next_page_token": next_token
    })


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
async def review_kyc(data: KYCReviewSchema, admin=Depends(admin_required)):
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


@rp.post("/mock/orders")
async def mock_orders(data: MockCreateOrderSchema):
    return await MockOrderService.simulate_orders(
        merchant_id=str(data.merchant_id),
        user_count=data.user_count,
        per_user=data.per_user,
    )
