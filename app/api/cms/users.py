"""
# @Time    : 2025/11/12 14:24
# @Author  : Pedro
# @File    : users.py
# @Software: PyCharm
"""

from fastapi import APIRouter, Depends, Request

from app.api.cms.model.user import User
from app.api.cms.schema.admin import DevicesStatusSchema
from app.api.cms.services.kyc_review_service import KYCService
from app.api.v1.schema.response import LoginSuccessResponse, UserInformationResponse
from app.api.v1.schema.user import LoginSchema, UserAgentSchema, UserInformationSchema, PageQuery, UserSchema
from app.api.cms.schema.users import InformationUpdateSchema
from app.api.cms.services.user_service import UserService
from app.extension.redis.redis_client import rds
from app.pedro.pedro_jwt import admin_required, jwt_service, FirebaseAuthService, login_required
from app.pedro.response import PedroResponse
from app.util.crypto import cipher

rp = APIRouter(prefix="/user", tags=["管理-商户"])


# ======================================================
# 🔐 登录并生成 Token
# ======================================================
@rp.post("/login", name="用户名登录", response_model=LoginSuccessResponse)
async def login(data: LoginSchema, request: Request):
    """
    用户登录并获取 Token
    """
    user = await UserService.get_by_username(data.username)

    if data.password_encrypted:
        data.password = cipher.decrypt(data.password)
    if not user:
        return PedroResponse.fail(code=10020, msg="用户不存在")
    if not await user.verify_password(data.password):
        return PedroResponse.fail(code=10030, msg="密码错误")

    tokens = await jwt_service.after_login_security(user, request, data)
    firebase_tokens = await FirebaseAuthService.create_custom_token(user.id)

    # 记录登录设备信息
    ua_string = request.headers.get("User-Agent", "")
    device_info = UserAgentSchema.from_ua(ua_string)

    await User.add_login_device(user.id, device_info.dict())

    return LoginSuccessResponse(**tokens, firebase_token=firebase_tokens)


@rp.get("/information", name="个人详情",
        response_model=UserInformationResponse[UserInformationSchema],
        dependencies=[Depends(admin_required)])
async def get_user_info(current_user: User = Depends(admin_required)):
    return UserInformationResponse.success(
        msg="个人信息获取成功",
        data=UserInformationSchema.smart_load(current_user)
    )


@rp.put("/{uid}", name="更新用户信息")
async def update_user_info(
        uid: int,
        payload: InformationUpdateSchema,
        current_user=Depends(admin_required)
):
    user = await User.get(uuid=uid)
    data = payload.model_dump(exclude_none=True)

    # ✅ 特殊 avatar
    if "avatar" in data:
        data["_avatar"] = data.pop("avatar")

    # ✅ extra 字段专门处理
    extra_fields = ("phone", "gender", "birthday", "points", "vip_status","kyc_status")
    extra_data = {k: data.pop(k) for k in list(data.keys()) if k in extra_fields}

    # ✅ 先更新普通字段
    if data:
        await user.update(commit=True, **data)

    # ✅ 再更新 extra 字段
    if extra_data:
        await user.update_extra(extra_data)

    return PedroResponse.success(msg="用户信息更新成功")


@rp.get("/")
async def get_users(page_query: PageQuery = Depends(),
                    keyword: str | None = None,
                    order_by: str = "id",
                    sort: str = "desc"):
    items, total = await UserService.list_users(
        keyword=keyword,
        order_by=order_by,
        sort=sort,
        page=page_query.page,
        size=page_query.size,
    )

    # ✅ 返回分页响应
    return PedroResponse.page(
        items=items,
        total=total,
        page=page_query.page,
        size=page_query.size,
        msg="用户列表获取成功",
    )


@rp.delete("/{uid}")
async def delete_user(uid: int, current_user=Depends(admin_required)):
    user = await User.get(uuid=uid)
    if not user:
        return PedroResponse.fail(msg="没有找到该用户")
    await user.delete(commit=True)
    return PedroResponse.success(msg="删除成功")


@rp.get('/kyc')
async def get_kyc_users(keyword: str | None = None):
    users = await KYCService.list_all_kyc_info()
    return users
