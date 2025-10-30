# -*- coding: utf-8 -*-
"""
统一登录后处理逻辑：记录设备、信任设备、生成 token、风控
"""
from fastapi import Request
from app.api.v1.schema.user import UserAgentSchema
from app.extension.redis.redis_client import rds
from app.pedro.pedro_jwt import jwt_service


async def after_login_security_handler(user, request: Request, payload):
    """
    登录后统一风控逻辑（账号密码 / 第三方登录 通用）
    不要改现有参数名
    """

    # ① 获取 UA + IP
    ip = request.client.host
    ua = request.headers.get("User-Agent", "")
    device = UserAgentSchema.from_ua(ua).model_dump()

    # ② 写入最近设备（最多 2）
    await user.jpush_unique_path(
        "sensitive.login_devices",
        device,
        unique_fields=["device", "browser", "os"],
        limit=2
    )

    # ③ 指纹
    fingerprint = jwt_service.make_fingerprint(ua, ip)

    # remember_me = True → 信任设备
    if getattr(payload, "remember_me", False):
        await jwt_service.trust_device(user.id, fingerprint, days=30)

    # ④ 生成 JWT token
    tokens = await jwt_service.create_pair(user, request)

    return tokens
