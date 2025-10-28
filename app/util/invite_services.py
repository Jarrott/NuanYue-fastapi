"""
# @Time    : 2025/10/28 3:31
# @Author  : Pedro
# @File    : invite_services.py
# @Software: PyCharm
"""
# -*- coding: utf-8 -*-
"""
Pedro-Core 邀请服务模块 (Async Version)
-----------------------------------------
✅ 异步 SQLAlchemy ORM (2.x)
✅ Redis 缓存（aioredis 封装）
✅ 防止循环邀请 / 自邀请
✅ 支持多级关系 (l1, l2, l3, ref_path)
"""

import random
import string
import json
from typing import Optional, Dict, Any

from sqlalchemy import select, func, update
from sqlalchemy.orm.attributes import flag_modified

from app.pedro.db import async_session_factory
from app.extension.redis.redis_client import rds
from app.api.cms.model.user import User
from app.util.redis_key_schema import redis_key_user_referral


# ======================================================
# 🎲 生成唯一邀请码
# ======================================================
async def generate_invite_code(length: int = 8, session=None) -> str:
    """生成唯一邀请码（异步查询验证）"""
    async def _exists(code: str) -> bool:
        stmt = select(User).where(
            User.extra["referral"]["invite_code"].astext == code
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none() is not None

    code = "".join(random.choices(string.ascii_uppercase + string.digits, k=length))
    while await _exists(code):
        code = "".join(random.choices(string.ascii_uppercase + string.digits, k=length))
    return code


# ======================================================
# 🎯 分配邀请码
# ======================================================
async def assign_invite_code(user: User) -> str:
    """
    为用户分配唯一邀请码并写入 extra.referral，同时同步到 Redis
    """
    async with async_session_factory() as session:
        # 刷新最新数据
        stmt = select(User).where(User.id == user.id)
        user = (await session.execute(stmt)).scalar_one_or_none()
        if not user:
            raise ValueError("用户不存在")

        user.extra = user.extra or {}
        referral = user.extra.get("referral", {}) or {}

        # 已存在邀请码
        if referral.get("invite_code"):
            print(f"⚠️ 用户 {user.id} 已存在邀请码: {referral['invite_code']}")
            return referral["invite_code"]

        code = await generate_invite_code(session=session)
        referral["invite_code"] = code
        user.extra["referral"] = referral
        flag_modified(user, "extra")

        await session.commit()
        # Redis 缓存（3天）
        key = redis_key_user_referral(user.id)
        await rds.set(key, json.dumps(referral, ensure_ascii=False),86400 * 3)

        print(f"✅ 用户 {user.id} 已分配邀请码: {code}")
        return code


# ======================================================
# 🔗 绑定邀请关系
# ======================================================
async def bind_inviter_relation(user: User, inviter_code: str):
    """
    注册时绑定邀请链关系（三级链 + ref_path）
    支持 SQLite/MySQL/PostgreSQL
    """
    async with async_session_factory() as session:
        # 查找邀请者
        stmt = select(User).where(
            User.extra['referral']['invite_code'].astext == inviter_code
        )
        inviter = (await session.execute(stmt)).scalar_one_or_none()
        if not inviter:
            raise ValueError("邀请码无效")

        # 防止自己邀请自己
        if inviter.id == user.id:
            raise ValueError("不能使用自己的邀请码注册")

        # 获取 inviter referral
        inviter_ref: Dict[str, Any] = {}
        inviter_key = redis_key_user_referral(inviter.id)
        cached = await rds.get(inviter_key)
        if cached:
            try:
                inviter_ref = json.loads(cached)
            except Exception:
                inviter_ref = inviter.extra.get("referral", {})
        else:
            inviter_ref = inviter.extra.get("referral", {})

        inviter_ref = inviter_ref or {}
        inviter_path = inviter_ref.get("ref_path", str(inviter.id))

        # 防止循环链
        if str(user.id) in inviter_path.split(">"):
            raise ValueError("非法邀请关系（检测到循环链）")

        # 构建新用户 referral 信息
        user_ref = {
            "inviter_id": inviter.id,
            "l1_id": inviter.id,
            "l2_id": inviter_ref.get("l1_id"),
            "l3_id": inviter_ref.get("l2_id"),
            "ref_path": f"{inviter_path}>{user.id}",
        }

        # 更新数据库
        stmt_user = update(User).where(User.id == user.id).values(
            extra=func.json_set(
                User.extra,
                "$.referral",
                json.dumps(user_ref, ensure_ascii=False),
            )
        )
        await session.execute(stmt_user)
        await session.commit()

        # 缓存关系（3天）
        key = redis_key_user_referral(user.id)
        await rds.setex(key, 86400 * 3, json.dumps(user_ref, ensure_ascii=False))

        print(f"✅ 用户 {user.id} 已绑定邀请关系 (上级: {inviter.id})")
        return user_ref
