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
import uuid
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
    MockCreateOrderSchema, PushMessageSchema, CreateHomeFlashSchema)

from app.api.cms.services.admin_ledger_service import AdminLedgerService
from app.api.cms.services.firebase_admin_service import FirebaseAdminService
from app.api.cms.services.flash_sale_service import create_home_flash_datetime_sale
from app.api.cms.services.kyc_review_service import KYCService
from app.api.cms.services.orders.mock_order_service import MockOrderService
from app.api.cms.services.user_wallet_service import AdminWalletService
from app.api.v1.schema.response import SuccessResponse
from app.api.cms.services.wallet.wallet_secure_service import WalletSecureService
from app.api.cms.services.wallet.wallet_sync_service import WalletSyncService
from app.api.v1.services.user_service import UserService
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
        {"msg": f"{msg}","envent":"broadcast"}
    )
    return SuccessResponse.success(msg="信息已成功推送")


@rp.post("/push/message/{uid}", response_model=SuccessResponse,
         dependencies=[Depends(admin_required)])
async def broadcast_user_message(uid: int, data: PushMessageSchema):
    await notify_user(uid, {
        "event": "otc_message",  # message_user,alert_message,order_message
        "msg": data.data
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
    reference = f"ADM-CR-{uuid.uuid4().hex[:12]}"

    # 1️⃣ 安全入账
    await WalletSecureService.credit_wallet_admin(
        uid=uid,
        amount=payload.amount,
        reference=reference,
        desc="管理员手动入账",
        operator_id=str(admin.username),
        remark="充值审核通过"
    )

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


@rp.post("/manual/debit", name="管理员手动（扣款）", dependencies=[Depends(admin_required)])
async def manual_debit_api(payload: ManualCreditSchema, admin=Depends(admin_required)):
    """
    管理员手动扣款（强同步 + 幂等）
    - Firestore 原子扣款 + Ledger
    - PostgreSQL / Redis / RTDB 多源同步
    """
    result = await WalletSecureService.debit_wallet_admin(
        uid=payload.user_id,
        amount=float(payload.amount),
        operator_id=admin.username,  # 记录后台操作者
        remark=payload.reason or "后台扣款",  # 备注
        # reference=payload.reference 如果你 schema 里有也可传入，保证幂等
    )
    return result  # 已是 PedroResponse(JSONResponse)


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
    status = "开启" if state == 1 else "关闭"
    return PedroResponse.success(msg=f"状态：{status}成功!")


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
    check = await KYCService.review_kyc(uid=str(uid), admin_id=admin.id, data=data)
    if not check:
        return PedroResponse.fail(msg="审核失败")
    # ✅ 更新 PGSQL 用户扩展字段
    user = await User.get(uuid=uid)
    new_status = KYCStatus.APPROVED.value if data.approve else KYCStatus.REJECTED.value
    await user.set_extra(kyc_status=new_status)

    return PedroResponse.success(
        msg=f"KYC审核{'通过' if data.approve else '拒绝'}"
    )


@rp.post("/flash/datetime")
async def create_home_flash(data:CreateHomeFlashSchema):
    flash_sale = await create_home_flash_datetime_sale(body=data)
    if not flash_sale:
        return PedroResponse.fail(msg="相同的秒杀任务已存在")
    return PedroResponse.success(msg=f"任务创建成功")


@rp.post("/mock/orders")
async def mock_orders(data: MockCreateOrderSchema):
    return await MockOrderService.simulate_orders(
        merchant_id=str(data.merchant_id),
        order_count=data.user_count,
        # per_user=data.per_user,
    )
