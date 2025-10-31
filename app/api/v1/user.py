# -*- coding: utf-8 -*-
"""
Pedro-Core FastAPI 用户模块 (Async Version)
---------------------------------------------
✅ 异步 SQLAlchemy ORM 操作
✅ Redis 缓存 / RabbitMQ 延迟任务
✅ JWT 登录认证
✅ 支持会员开通、签到、邀请关系树
"""
from fastapi import APIRouter, Depends, HTTPException, Request

from sqlalchemy import select
from firebase_admin import auth as firebase_auth

from app.pedro.pedro_jwt import jwt_service

from app.api.v1.schema.response import (
    SuccessResponse,
    LoginSuccessResponse,
    GoogleLoginSuccessResponse,
    UserInformationResponse, GoogleUserInfo, DepositCreateResponse)
from app.api.v1.services.auth_service import AuthService
from app.api.v1.services.deposit_service import DepositService
from app.api.v1.services.user_service import UserService
from user_agents import parse

from app.extension.websocket.wss import websocket_manager
from app.pedro import UserGroup
# from PIL import Image, ImageDraw, ImageFont

from app.pedro.db import async_session_factory
from app.pedro.exception import UnAuthentication
from app.pedro.pedro_jwt import jwt_service, login_required, admin_required
from app.config.settings_manager import get_current_settings
from app.api.v1.schema.user import (
    UserRegisterSchema,
    LoginSchema,
    UserInformationSchema, OTCDepositSchema, UserAgentSchema,
)

from app.api.cms.model.user import User
from app.api.cms.model.user_group import UserGroup
from app.util.invite_services import assign_invite_code, bind_inviter_relation

rp = APIRouter(prefix="/user", tags=["用户"])
settings = get_current_settings()


# ======================================================
# 🧩 注册新用户
# ======================================================
@rp.post("/register", name="用户注册",response_model=SuccessResponse)
async def register_user(payload: UserRegisterSchema):
    # 用户名唯一性校验
    if await UserService.get_by_username(payload.username):
        raise HTTPException(status_code=400, detail="用户名重复")

    await UserService.create_user_ar(
        username=payload.username,
        password=payload.password,
        inviter_code=payload.inviter_code,
        group_ids=payload.group_ids,
    )
    return SuccessResponse(msg="注册成功")


# ======================================================
# 🔐 登录并生成 Token
# ======================================================
@rp.post("/login",name="用户名登录", response_model=LoginSuccessResponse)
async def login(data: LoginSchema, request: Request):
    """
    用户登录并获取 Token
    """
    user = await UserService.get_by_username(data.username)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    if not await user.verify_password(data.password):
        raise HTTPException(status_code=401, detail="密码错误")

    tokens = await jwt_service.after_login_security(user, request, data)


    # 记录登录设备信息
    ua_string = request.headers.get("User-Agent", "")
    device_info = UserAgentSchema.from_ua(ua_string)

    await User.add_login_device(user.id, device_info.dict())

    return LoginSuccessResponse(**tokens)


@rp.post("/google/login", name="谷歌登陆",response_model=GoogleLoginSuccessResponse)
async def google_login(payload: dict, request: Request):
    g = AuthService.verify_google_token(payload.get("id_token"))
    user = await UserService.get_by_username(g["email"])
    # 记录登录设备信息
    ua_string = request.headers.get("User-Agent", "")
    device_info = UserAgentSchema.from_ua(ua_string)

    await User.add_login_device(user.id, device_info.dict())
    if not user:
        user = await UserService.create_user_ar(
            username=g["email"],
            email=g["email"],
            name=g["name"] or g["email"].split("@")[0],
            avatar=g["picture"],
            inviter_code=payload.get("inviter_code"),
            group_ids=payload.get("group_ids"),
        )
    tokens = await AuthService.create_tokens(user)

    # 谷歌登录
    user_info = GoogleUserInfo(
        uid=g["uid"],
        email=g["email"],
        name=g["name"],
        avatar=g["picture"],
    )

    return GoogleLoginSuccessResponse(**tokens, user=user_info)


@rp.get("/information",name="个人详情",
        response_model=UserInformationResponse[UserInformationSchema],
        dependencies=[Depends(login_required)])
def get_user_info(current_user: User = Depends(login_required)):
    return UserInformationResponse(
        data=UserInformationSchema.smart_load(current_user)
    )


# @rp.get("/user", dependencies=[Depends(login_required)])
# async def user_access():
#     """所有登录用户可访问"""
#     return {"msg": "✅ 普通用户接口访问成功"}
#
#
# @rp.get("/admin", dependencies=[Depends(admin_required)])
# async def admin_access():
#     """仅管理员可访问"""
#     return {"msg": "🛡️ 管理员接口访问成功"}


@rp.get("/push/message",name="推送信息给客服")
async def broadcast_system_announcement():
    await websocket_manager.broadcast_all("🚨 系统将在 10 分钟后进行维护，请及时保存工作。")
    print(f"📣 已全局广播系统消息: ")


@rp.post("/deposit/otc",name="充值方式", response_model=DepositCreateResponse)
async def submit_otc(payload: OTCDepositSchema, current_user=Depends(login_required)):
    key, deposit = await DepositService.submit_manual_order(
        user_id=current_user.id,
        amount=payload.amount,
        token=payload.token,
        proof=payload.proof_image
    )

    return DepositCreateResponse(order_number=deposit.order_no)

@rp.get("/order/detail/{order_no}",name="查看订单详情")
async def order_detail():
    pass

@rp.get("/shops/detail",name="查看商品详情")
async def product_detail():
    pass

@rp.get("/ads",name="轮播图")
def ads():
    pass

@rp.get("/shops",name="商品列表")
def ads():
    pass

@rp.get("/kyc",name="用户认证")
def ads():
    pass