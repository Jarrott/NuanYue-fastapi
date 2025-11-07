"""
# @Time    : 2025/11/6 3:47
# @Author  : Pedro
# @File    : merchant.py
# @Software: PyCharm
"""
from fastapi import APIRouter, Depends

from app.api.cms.model import User
from app.api.cms.schema.admin import DevicesStatusSchema
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


