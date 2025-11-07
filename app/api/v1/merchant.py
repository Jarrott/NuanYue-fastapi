"""
# @Time    : 2025/11/6 4:27
# @Author  : Pedro
# @File    : merchant.py
# @Software: PyCharm
"""
from fastapi import APIRouter, Depends

from app.api.cms.model import User
from app.api.v1.schema.merchant import MerchantProfile, WalletVO, WithdrawCreate, LogsQuery, CreateStoreSchema, \
    PurchaseSchema
from app.api.v1.schema.response import StoreDetailResponse
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

@rp.post("/", name="统一采购接口（支持单/批量）")
async def purchase(data: PurchaseSchema, user=Depends(login_required)):
    """
    如果传入 product_id 和 quantity → 走单商品采购；
    如果传入 items 数组 → 走批量采购；
    如果两者都有 → 优先 items。
    """
    uid = str(user.id)

    # ✅ 批量采购优先
    if data.items:
        return await MerchantService.purchase_batch(uid=uid, items=data.items)

    # ✅ 单商品采购
    if data.product_id and data.quantity:
        return await MerchantService.purchase_single(
            uid=uid,
            product_id=data.product_id,
            quantity=data.quantity
        )

    return PedroResponse.fail(msg="参数错误：请传入 (product_id, quantity) 或 items[]")
