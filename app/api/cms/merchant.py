"""
# @Time    : 2025/11/6 3:47
# @Author  : Pedro
# @File    : merchant.py
# @Software: PyCharm
"""
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.params import Query

from app.api.cms.model import User
from app.api.cms.schema.admin import DevicesStatusSchema
from app.api.cms.services.store.store_service import AdminStoreService
from app.api.v1.services.store_service import MerchantService
from app.extension.redis.redis_client import rds
from app.pedro.pedro_jwt import admin_required
from app.pedro.response import PedroResponse

rp = APIRouter(prefix="/merchant", tags=["管理-商户"])


@rp.put("/devices", name="商家设备验证管理")
async def admin_device_verify(data: DevicesStatusSchema, admin=Depends(admin_required)):
    uid = data.user_id
    r = await rds.instance()
    user = await User.get(id=uid)
    status = "1" if data.approve else "0"
    # 关闭验证
    # await r.set(f"user:{uid}:device_lock", "0")
    await r.set(f"user:{uid}:device_lock", status)  # 开启
    user.extra.device_lock = data.approve
    await user.update(commit=True)

    return PedroResponse.success(msg=f"设备验证{"开启" if data.approve else "关闭"}成功!")


@rp.get("/")
async def get_merchant():
    merchants = await MerchantService.list_all_store_applications()
    return merchants

# ======================================================
# 🧾 后台：查看所有商户采购记录（跨商户，含全部状态）
# ======================================================
@rp.get("/purchases")
async def admin_list_purchases(
    status: Optional[str] = Query(None, description="订单状态：pending/purchased/delivered/completed"),
    keyword: Optional[str] = Query(None, description="关键字模糊搜索（订单号/买家信息/商品名等）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=200, description="每页数量")
):
    """
    🧾 查看所有商家的采购记录（支持状态 & 关键字 & 分页）
    -----------------------------------------------------
    使用 Firestore collection_group("orders") 跨所有商户目录查询。
    """
    return await AdminStoreService.list_all_purchase_records(
        status=status,
        keyword=keyword,
        page=page,
        page_size=page_size
    )