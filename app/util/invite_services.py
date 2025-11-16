"""
# @Time    : 2025/10/28 3:31
# @Author  : Pedro
# @File    : invite_services.py
# @Software: PyCharm
"""

import random
import string
import json
from typing import Optional, Dict, Any

from sqlalchemy import select, func, update, text, cast
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.dialects.postgresql import JSONB

from app.pedro.db import async_session_factory
from app.extension.redis.redis_client import rds
from app.api.cms.model.user import User
from app.util.redis_key_schema import redis_key_user_referral


# ======================================================
# 🎲 生成唯一邀请码
# ======================================================
async def generate_invite_code(length: int = 8) -> str:
    """生成唯一邀请码（内部会自动检查 DB 是否重复）"""

    async with async_session_factory() as session:

        async def _exists(code: str) -> bool:
            stmt = select(User).where(
                User.extra["invite_code"].astext == code
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
    为用户生成并写入唯一邀请码（写入 extra.referral.invite_code）
    """

    extra = user.extra or {}
    referral = extra.get("referral") or {}

    # 已存在则直接返回
    if referral.get("invite_code"):
        return referral["invite_code"]

    # 生成唯一邀请码（自动确保唯一）
    code = await generate_invite_code()

    # 写入 referral 结构
    referral["invite_code"] = code

    # 回写到 extra
    extra["referral"] = referral

    # 使用 ActiveRecord 更新数据库
    await user.update(extra=extra, commit=True)

    # 写入 Redis，存储 referral 部分，不存整个 extra
    redis = await rds.instance()
    key = redis_key_user_referral(user.id)
    await redis.setex(key, 86400 * 3, json.dumps(referral, ensure_ascii=False))

    print(f"🟢 用户 {user.id} 已分配邀请码: {code}")
    return code


# ======================================================
# 🔗 绑定邀请关系
# ======================================================
async def bind_inviter_relation(user: User, inviter_code: str) -> Dict[str, Any]:
    """
    注册时绑定邀请链关系（三级链 + ref_path）

    结构写入路径：extra.referral
    {
        "invite_code": "XXXXXX",   # 自己的邀请码（assign_invite_code 写入）
        "inviter_id": 34,          # 直推上级
        "l1_id": 34,               # 一级
        "l2_id": 21,               # 二级
        "l3_id": 7,                # 三级
        "ref_path": "7>21>34>38",  # 完整路径
    }
    """

    # ① 先从 DB 查询邀请码对应的上级
    async with async_session_factory() as session:
        stmt = select(User).where(
            User.extra["referral"]["invite_code"].astext == inviter_code
        )
        inviter: User | None = (await session.execute(stmt)).scalar_one_or_none()

    if not inviter:
        raise ValueError("邀请码无效")

    # ② 防止自己邀请自己
    if inviter.uuid == user.uuid:
        raise ValueError("不能使用自己的邀请码注册")

    # ③ 读取上级 referral（Redis 优先）
    redis = await rds.instance()
    inviter_key = redis_key_user_referral(inviter.id)

    inviter_ref: Dict[str, Any] = {}
    cached = await redis.get(inviter_key)
    if cached:
        try:
            inviter_ref = json.loads(cached)
        except Exception:
            inviter_ref = inviter.extra.get("referral", {}) or {}
    else:
        inviter_ref = inviter.extra.get("referral", {}) or {}

    # 上级现有路径（可能是 "" / None / "7>21>34"）
    raw_path = inviter_ref.get("ref_path")
    inviter_path = raw_path if raw_path else None

    # ④ 防止循环链
    if inviter_path:
        segments = inviter_path.split(">")
        if str(user.id) in segments:
            raise ValueError("非法邀请关系（检测到循环链）")

    # ⑤ 生成当前用户的 ref_path
    if inviter_path:
        ref_path = f"{inviter_path}>{user.id}"
    else:
        # 上级没有路径 → 说明上级是链路起点
        ref_path = f"{inviter.id}>{user.id}"

    # ⑥ 构建当前用户的 referral 信息
    user_ref: Dict[str, Any] = {
        "inviter_id": inviter.id,
        "l1_id": inviter.id,
        "l2_id": inviter_ref.get("l1_id"),
        "l3_id": inviter_ref.get("l2_id"),
        "ref_path": ref_path,
    }

    # ⑦ 合并写入当前用户 extra.referral（ActiveRecord 模式）
    extra: Dict[str, Any] = user.extra or {}
    current_referral = extra.get("referral") or {}
    current_referral.update(user_ref)
    extra["referral"] = current_referral

    await user.update(extra=extra, commit=True)

    # ⑧ 写入 Redis 缓存（3 天）
    key = redis_key_user_referral(user.id)
    await redis.setex(key, 86400 * 3, json.dumps(current_referral, ensure_ascii=False))


    print(
        f"✅ 用户 {user.id} 已绑定邀请关系 "
        f"(上级: {inviter.id}, 路径: {current_referral['ref_path']})"
    )
    return current_referral