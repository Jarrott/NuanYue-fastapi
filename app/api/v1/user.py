# -*- coding: utf-8 -*-
"""
Pedro-Core FastAPI 用户模块 (Async Version)
---------------------------------------------
✅ 异步 SQLAlchemy ORM 操作
✅ Redis 缓存 / RabbitMQ 延迟任务
✅ JWT 登录认证
✅ 支持会员开通、签到、邀请关系树
"""

import json
import time
from datetime import datetime, timedelta
from io import BytesIO
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, Request, UploadFile, File, HTTPException, status, Body
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.handler.response import SuccessResponse, LoginSuccessResponse
from app.pedro import manager, UserGroup
# from PIL import Image, ImageDraw, ImageFont

from app.pedro.db import async_session_factory
from app.pedro.exception import UnAuthentication
from app.pedro.manager import Manager
from app.pedro.pedro_jwt import jwt_service, login_required, admin_required
from app.extension.redis.redis_client import rds
from app.config.settings_manager import get_current_settings
from app.api.v1.schema.user import (
    UserRegisterSchema,
    LoginSchema,
    LoginTokenSchema,
)
from app.api.cms.model.user import User
from app.api.cms.model.user_group import UserGroup
from app.util.invite_services import assign_invite_code, bind_inviter_relation

rp = APIRouter(prefix="/user", tags=["用户"])
settings = get_current_settings()


# ======================================================
# 🧩 注册新用户
# ======================================================
@rp.post("/register", response_model=SuccessResponse)
async def register_user(payload: UserRegisterSchema):
    async with async_session_factory() as session:
        # 检查用户名 / 邮箱是否重复
        stmt = select(User).where(User.username == payload.username)
        if (await session.execute(stmt)).scalar_one_or_none():
            raise UnAuthentication("用户名重复")
        user = User(username=payload.username)
        session.add(user)
        await session.flush()
        await user.set_password(payload.password)
        await session.commit()

        await assign_invite_code(user)
        if payload.inviter_code is not None:
            await bind_inviter_relation(user, payload.inviter_code)

        if len(payload.group_ids) == 0:
            from app.pedro.enums import GroupLevelEnum

            group_ids = [GroupLevelEnum.GUEST.value]

        group_ids = payload.group_ids
        for group_id in group_ids:
            user_group = UserGroup()
            user_group.user_id = user.id
            user_group.group_id = group_id
            session.add(user_group)
            await session.commit()


        return SuccessResponse(msg="注册成功")


# ======================================================
# 🔐 登录并生成 Token
# ======================================================
@rp.post("/login", response_model=LoginSuccessResponse)
async def login(data: LoginSchema):
    """
    用户登录并获取 Token
    """
    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.username == data.username)
        )
        user = result.scalar_one_or_none()

        # 用户不存在
        if not user:
            raise UnAuthentication("用户不存在")

        # 校验密码（取决于你的 User 模型）
        if not await user.verify_password(data.password):
            raise UnAuthentication("密码错误")

        # ✅ 创建 JWT token
        tokens = await jwt_service.create_pair(user)

        return LoginSuccessResponse(access_token=tokens["access_token"], refresh_token=tokens["refresh_token"])


@rp.get("/user", dependencies=[Depends(login_required)])
async def user_access():
    """所有登录用户可访问"""
    return {"msg": "✅ 普通用户接口访问成功"}

@rp.get("/admin", dependencies=[Depends(admin_required)])
async def admin_access():
    """仅管理员可访问"""
    return {"msg": "🛡️ 管理员接口访问成功"}
#
# # ======================================================
# # 👤 获取当前用户信息（Redis 缓存）
# # ======================================================
# @router.get("/information", response_model=UserOutSchema)
# async def get_user_info(current_user: User = Depends(get_current_user)):
#     cache_key = f"user:cache:{current_user.id}"
#     cached = await rds.get(cache_key)
#     if cached:
#         try:
#             return json.loads(cached)
#         except Exception:
#             pass
#
#     async with async_session_factory() as session:
#         stmt = select(User).where(User.id == current_user.id)
#         user = (await session.execute(stmt)).scalar_one_or_none()
#         if not user:
#             raise HTTPException(status_code=404, detail="用户不存在")
#
#         user_data = serialize_user_extra(user)
#         await rds.setex(cache_key, 180, json.dumps(user_data, ensure_ascii=False))
#         return user_data
#
#
# # ======================================================
# # ✏️ 更新用户信息
# # ======================================================
# @router.patch("/information")
# async def update_user_info(
#     payload: UserUpdateSchema, current_user: User = Depends(get_current_user)
# ):
#     async with async_session_factory() as session:
#         stmt = select(User).where(User.id == current_user.id)
#         user = (await session.execute(stmt)).scalar_one_or_none()
#         if not user:
#             raise HTTPException(status_code=404, detail="用户不存在")
#
#         merge_user_extra(user, payload.information)
#         await session.commit()
#         await rds.delete(f"user:cache:{user.id}")
#         return {"message": "更新成功"}
#
#
# # ======================================================
# # 💎 开通或续费会员
# # ======================================================
# @router.post("/vip/purchase")
# async def purchase_vip(current_user: User = Depends(get_current_user)):
#     now = datetime.utcnow()
#     new_expire = now + timedelta(days=30)
#     async with async_session_factory() as session:
#         stmt = select(User).where(User.id == current_user.id)
#         user = (await session.execute(stmt)).scalar_one()
#         merge_user_extra(user, {"vip_expire_at": new_expire.isoformat()})
#         await session.commit()
#
#     ttl = int((new_expire - now).total_seconds())
#     await rds.setex(f"vip:uid:{current_user.id}", ttl, new_expire.isoformat())
#     return {"message": "VIP 已开通", "expires_at": new_expire.isoformat()}
#
#
# # ======================================================
# # 🎨 动态头像
# # ======================================================
# @router.get("/avatar/{char}")
# async def generate_avatar(char: str, c: int = 0):
#     colors = ["#4A90E2", "#50E3C2", "#F5A623", "#9013FE", "#D0021B", "#417505"]
#     bg_color = colors[c % len(colors)]
#     size = 256
#     img = Image.new("RGB", (size, size), bg_color)
#     draw = ImageDraw.Draw(img)
#     draw.ellipse([(0, 0), (size, size)], fill=bg_color)
#
#     text = char[0].upper()
#     font = ImageFont.load_default()
#     w, h = draw.textsize(text, font=font)
#     draw.text(((size - w) / 2, (size - h) / 2 - 10), text, fill="white", font=font)
#
#     buf = BytesIO()
#     img.save(buf, format="PNG")
#     buf.seek(0)
#     return StreamingResponse(buf, media_type="image/png")
#
#
# # ======================================================
# # 🔗 邀请关系树
# # ======================================================
# @router.get("/invite/tree")
# async def get_referral_tree(current_user: User = Depends(get_current_user)):
#     uid = current_user.id
#     key = f"user:invite_tree:{uid}"
#     cached = await rds.get(key)
#     if cached:
#         return json.loads(cached)
#
#     async with async_session_factory() as session:
#         stmt = select(User).where(func.instr(User.extra, f'"ref_path": "{uid}>') > 0)
#         result = await session.execute(stmt)
#         users = result.scalars().all()
#         data = [serialize_user_extra(u) for u in users]
#
#     await rds.setex(key, 10800, json.dumps(data, ensure_ascii=False))
#     return {"children": data}
#
#
# # ======================================================
# # 🔥 VIP 测试任务 (RabbitMQ 延迟消息)
# # ======================================================
# @router.get("/push/vip")
# async def push_vip(uid: int = 7, duration: int = 10):
#     expire_timestamp = int(time.time()) + duration
#     await publish_message(
#         queue="vip_expired",
#         data={"uid": uid, "event": "vip_expired", "expire_time": expire_timestamp},
#         delay=duration * 1000,
#     )
#     await rds.setex(f"vip_expired:user:{uid}", duration, "VIP")
#     return {"message": f"VIP 开通 {duration} 秒", "expire_in": duration}
#
#
# # ======================================================
# # 💰 获取 TRON 地址
# # ======================================================
# @router.get("/usdt/address")
# async def get_usdt_address(current_user: User = Depends(get_current_user)):
#     address = await get_user_tron_wallet(current_user.id)
#     return {"address": address}
