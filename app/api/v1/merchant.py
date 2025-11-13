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
from app.api.v1.services.store.store_review import StoreReviewService
from app.api.v1.services.store_order_service import RestockService
from app.api.v1.services.store_service import MerchantService
from app.extension.google_tools.firestore import fs_service
from app.extension.redis.redis_client import rds
from app.pedro.enums import KYCStatus
from app.pedro.pedro_jwt import login_required
from app.pedro.response import PedroResponse
from app.pedro.response_adapter import PedroResponseAdapter as R

rp = APIRouter(prefix="/merchant", tags=["商家模块"])


@rp.post("/create", name="商家创建商铺")
async def create_merchant(data: CreateStoreSchema, user=Depends(login_required)):
    """
    初始化创建商户 (Firestore)
    """
    r = await rds.instance()
    status_key = f"user:{user.uuid}:store:status"

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
        existing_store = await fs_service.get(f"users/{user.uuid}/store/profile")
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
        uid=user.uuid,
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


@rp.get("/profile", response_model=PedroResponse[list[StoreDetailResponse]])
async def profile(user=Depends(login_required)):
    data = await MerchantService.get_my_store(str(user.uuid))
    return PedroResponse.success(data=data,schema=CreateStoreSchema)


@rp.get("/wallet", response_model=WalletVO)
async def wallet(user=Depends(login_required)):
    data = await MerchantService.get_or_create_wallet(str(user.uuid))
    return PedroResponse.success(data=data,schema=WalletVO)


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
    """
    🔹 分页查询商户采购记录
    🔹 兼容 Firestore 结构（每批次内含 items）
    🔹 自动补齐商品详情
    """
    result = await MerchantService.list_purchase_batches(user.uuid, size)

    # ✅ 防止返回 PedroResponse / JSONResponse 导致 TypeError
    if isinstance(result, dict):
        data_block = result.get("data", result)
    elif hasattr(result, "body"):
        import json
        data_block = json.loads(result.body.decode()).get("data", {})
    else:
        data_block = {}

    batches = data_block.get("items", [])

    # 🔹 时间字段序列化
    def normalize(obj):
        if isinstance(obj, _helpers.DatetimeWithNanoseconds):
            return obj.isoformat()
        if isinstance(obj, dict):
            return {k: normalize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [normalize(v) for v in obj]
        return obj

    items = [normalize(doc) for doc in batches]

    # ✅ 标准分页返回
    total = data_block.get("total", len(items))
    return PedroResponse.page(
        page=page,
        size=size,
        total=total,
        items=items
    )

@rp.get("/orders/need-purchase", summary="查询需要进货的订单列表")
async def list_need_purchase_orders(
        page: int = Query(default=1, ge=1),
        size: int = Query(default=50, ge=1, le=100),
        user=Depends(login_required)
):
    result = await MerchantService.list_need_purchase_orders(user.uuid, size)
    return R.page(result, page=page, size=size)


@rp.post("/restock/single", summary="单独补货指定订单")
async def restock_single(
        order_id: str = Body(..., embed=True, description="订单ID"),
        user=Depends(login_required)
):
    """
    🔹 单独补货接口（扣款 + Firestore + RTDB 同步）
    🔹 用于单条缺货订单的补货操作
    """
    return await RestockService.restock_single(uid=str(user.uuid), order_id=order_id)


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
        result = await RestockService.restock_all(str(user.uuid))
        return result
    except Exception as e:
        print(f"[❌ Auto Restock Error] {e}")
        return PedroResponse.fail(msg=f"补货失败：{e}")

@rp.get("/reviews")
async def list_my_reviews(
    min_rating: float | None = Query(None),
    keyword: str | None = Query(None),
    has_image: bool | None = Query(None),
    size: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None),
    user=Depends(login_required),
):
    return await StoreReviewService.list_merchant_reviews(
        merchant_id=str(user.uuid or user.id),
        size=size,
        keyword=keyword,
        min_rating=min_rating,
        has_image=has_image,
        cursor=cursor,
    )