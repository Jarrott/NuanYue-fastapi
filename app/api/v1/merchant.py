"""
# @Time    : 2025/11/6 4:27
# @Author  : Pedro
# @File    : merchant.py
# @Software: PyCharm
"""
from fastapi import APIRouter, Depends, Query, Body
from google.cloud.firestore_v1 import _helpers

from app.api.cms.model import User
from app.api.v1.schema.merchant import (MerchantProfile,
                                        WalletVO,
                                        WithdrawCreate,
                                        LogsQuery,
                                        CreateStoreSchema,
                                        PurchaseSchema, PageQuery)

from app.api.v1.schema.response import StoreDetailResponse
from app.api.v1.services.store_order_service import RestockService
from app.api.v1.services.store_service import MerchantService
from app.extension.google_tools.firestore import fs_service
from app.extension.redis.redis_client import rds
from app.pedro.enums import KYCStatus
from app.pedro.pedro_jwt import login_required
from app.pedro.response import PedroResponse

rp = APIRouter(prefix="/merchant", tags=["商家模块"])


@rp.post("/create", name="商家创建商铺")
async def create_merchant(data: CreateStoreSchema, user=Depends(login_required)):
    """
    初始化创建商户 (Firestore)
    """
    r = await rds.instance()
    status_key = f"user:{user.id}:store:status"

    # ===================================================
    # ① 优先读取 Redis（减少 Firestore 成本）
    # ===================================================
    try:
        status = await r.get(status_key)
        if status:
            status = status.decode() if isinstance(status, bytes) else status
            status_messages = {
                "approved": "您已经拥有店铺！",
                "pending": "您的店铺申请正在审核中，请耐心等待。",
                "rejected": "您的开店申请已被拒绝，请联系客服。",
            }
            if msg := status_messages.get(status):
                return PedroResponse.fail(msg=msg)
    except Exception as e:
        # Redis 可能超时、断开连接
        print(f"⚠️ Redis 状态读取失败，回退到 Firestore：{e}")

    # ===================================================
    # ② Redis 未命中 / 异常时，读取 Firestore 实时状态
    # ===================================================
    try:
        existing_store = await fs_service.get(f"users/{user.id}/store/profile")
        fs_status = (existing_store or {}).get("status")

        if fs_status in ("pending", "approved"):
            # 同步回 Redis（缓存修复）
            await r.set(status_key, fs_status)
            return PedroResponse.fail(msg=f"您的店铺当前状态为「{fs_status}」，无法重复创建。")
    except Exception as e:
        print(f"⚠️ Firestore 状态读取失败：{e}")

    # ===================================================
    # ③ 检查用户 KYC 状态
    # ===================================================
    db_user = await User.get(id=user.id)
    kyc_status = (
        db_user.extra.get("kyc_status")
        if isinstance(db_user.extra, dict)
        else getattr(db_user.extra, "kyc_status", None)
    )

    if kyc_status != KYCStatus.APPROVED.value:
        return PedroResponse.fail(msg="请先通过个人认证！")

    # ===================================================
    # ④ 创建商户记录
    # ===================================================
    await MerchantService.create_merchant(
        uid=user.id,
        name=data.name or None,
        email=data.email or db_user.email,
        address=data.address or None,
        logo=data.logo or None,
    )

    # ===================================================
    # ⑤ 写入 Redis 缓存状态（带过期时间，防止长期脏数据）
    # ===================================================
    await r.setex(status_key, 86400 * 3, "pending")  # 有效期 3 天

    return PedroResponse.success(msg="店铺创建成功，等待审核")


@rp.get("/profile", response_model=StoreDetailResponse)
async def profile(user=Depends(login_required)):
    data = await MerchantService.get_profile(str(user.id))
    return PedroResponse.success(data)


@rp.get("/wallet", response_model=WalletVO)
async def wallet(user=Depends(login_required)):
    data = await MerchantService.get_wallet(str(user.id))
    return PedroResponse.success(data=data)


@rp.post("/withdraw")
async def withdraw(payload: WithdrawCreate, user=Depends(login_required)):
    data = await MerchantService.create_withdraw(
        uid=str(user.id),
        store_id=str(user.store_id),
        amount=payload.amount,
        method=payload.method,
        bank_account=payload.bank_account
    )
    return PedroResponse.success(data=data, msg="提现申请已提交")


@rp.post("/logs")
async def logs(query: LogsQuery, user=Depends(login_required)):
    items, _ = await MerchantService.list_logs(
        store_id=str(user.store_id),
        ltype=query.type,
        page=query.page,
        size=query.size
    )
    return PedroResponse.page(items=items, total=len(items), page=query.page, size=query.size)


# ====================================================
# 🧾 批量采购（后台或商家操作）
# ====================================================
@rp.post("/purchase")
async def purchase_items(data: PurchaseSchema, user=Depends(login_required)):
    return await MerchantService.purchase_batch(user.id, data.items)


# ====================================================
# 📜 查询采购列表（商家端前台）
# ====================================================
@rp.get("/purchases", summary="查询采购记录（分页）")
async def list_purchases(
        page: int = Query(default=1, ge=1),
        size: int = Query(default=20, ge=1, le=100),
        user=Depends(login_required)
):
    docs = await MerchantService.list_purchase_batches(user.id, size)

    def normalize(obj):
        from google.cloud.firestore_v1 import _helpers
        if isinstance(obj, _helpers.DatetimeWithNanoseconds):
            return obj.isoformat()
        if isinstance(obj, dict):
            return {k: normalize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [normalize(v) for v in obj]
        return obj

    data = [normalize(doc) for doc in docs]

    # ✅ PedroResponse.page 需要: page, size, total, items
    return PedroResponse.page(
        page=page,
        size=size,
        total=len(data),
        items=data
    )


# ====================================================
# 🔍 查询采购详情
# ====================================================
@rp.get("/purchase/{batch_id}")
async def purchase_detail(uid: str, batch_id: str):
    return await MerchantService.get_purchase_batch_detail(uid, batch_id)


# ✅ 原采购逻辑
@rp.post("/{uid}/purchase/batch")
async def merchant_purchase(uid: str, body: dict = Body(...)):
    return await MerchantService.purchase_batch(uid, body["items"])


# =========================================================
# ✅ 查询缺货订单（分页）
# =========================================================
@rp.get("/restock/orders")
async def get_need_purchase_orders(
    uid: str = Query(..., description="商户ID"),
    page: int = Query(1, description="页码", ge=1),
    size: int = Query(20, description="每页大小", le=100),
):
    """
    🔍 获取商户缺货订单列表
    - 支持分页（Firestore startAfter 游标）
    """
    orders, next_cursor = await RestockService.list_need_purchase_orders_paged(uid, limit=size)
    return PedroResponse.page(
        msg=f"找到 {len(orders)} 个缺货订单",
        items=orders,
        total=len(orders),
        page=page,
        size=size,
        cursor=next_cursor,
    )


# =========================================================
# ✅ 一键补货（自动扣款 + 更新库存 + Firestore 同步）
# =========================================================
@rp.post("/restock/auto")
async def auto_restock(user=Depends(login_required)):
    """
    💰 一键补货
    - 自动计算所有 need_purchase 订单
    - 按 price/discount/rating 动态定价
    - 扣除钱包金额
    - 更新 Firestore / RTDB
    - 订单状态变更为 pending
    """
    try:
        result = await RestockService.restock_all(user.id)
        return result
    except Exception as e:
        print(f"[❌ Auto Restock Error] {e}")
        return PedroResponse.fail(msg=f"补货失败：{e}")