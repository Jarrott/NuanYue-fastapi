# -*- coding: utf-8 -*-
"""
# @Time    : 2025/11/14 00:35
# @Author  : Pedro
# @File    : user_service.py
# @Software: PyCharm
"""
from typing import Optional, Tuple, List
from app.api.cms.model.user import User
from app.extension.redis.redis_client import rds


class UserService:
    """
    🧩 Pedro-Core 用户服务层（增强版）
    ------------------------------------------------
    ✅ 支持分页 / 搜索 / 排序
    ✅ 展开 extra 信息（balance, points, referral, settings）
    ✅ 实时在线状态（Redis 统一）
    ✅ UUID / UID 混用自动兜底
    """

    @staticmethod
    async def list_users(
        *,
        keyword: Optional[str] = None,
        level: Optional[str] = None,
        status: Optional[int] = None,
        order_by: str = "id",
        sort: str = "desc",
        page: int = 1,
        size: int = 10,
    ) -> Tuple[List[dict], int]:
        """
        🔍 获取用户列表（包含扩展字段 + 实时在线状态）
        """
        filters = {"level": level, "status": status}
        keyword_fields = ["username", "email", "phone"]

        users, total = await User.paginate(
            page=page,
            size=size,
            filters=filters,
            keyword=keyword,
            keyword_fields=keyword_fields,
            order_by=order_by,
            sort=sort,
        )

        r = await rds.instance()
        results = []

        # ✅ 批量取在线集合（sismember）+ 详情哈希（hget）
        pipeline = r.pipeline()
        for u in users:
            uid = str(getattr(u, "id", None) or getattr(u, "uuid", None))
            pipeline.sismember("ws:online:uids", uid)
            pipeline.hget(f"ws:online:detail:{uid}", "last_seen")
        redis_results = await pipeline.execute()

        for i, u in enumerate(users):
            uid = str(getattr(u, "uuid", None) or getattr(u, "id", None))
            is_online = bool(redis_results[i * 2])
            last_seen = redis_results[i * 2 + 1]
            if isinstance(last_seen, bytes):
                last_seen = last_seen.decode()

            # 🧩 extra 信息
            extra = getattr(u, "extra", {}) or {}
            referral = extra.get("referral", {}) or {}
            settings = extra.get("settings", {}) or {}
            sensitive = extra.get("sensitive", {}) or {}

            results.append({
                "id": u.id,
                "uuid": str(u.uuid),
                "username": u.username,
                "email": u.email,
                "avatar": u.avatar,
                "register_type": u.register_type,
                "status": getattr(u, "status", None),
                "created_at": getattr(u, "created_at", None),
                "last_login": getattr(u, "last_login", None),

                # 🪙 扩展字段
                "balance": extra.get("balance", 0.0),
                "points": extra.get("points", 0),
                "currency": extra.get("currency", "USD"),
                "phone": extra.get("phone"),
                "gender": extra.get("gender"),
                "birthday": extra.get("birthday"),
                "kyc_status": extra.get("kyc_status", 0),
                "vip_status": extra.get("vip_status", False),
                "vip_expire_at": extra.get("vip_expire_at"),
                "is_merchant": extra.get("is_merchant", False),

                # 👥 推荐人链路
                "referral": {
                    "invite_code": referral.get("invite_code"),
                    "ref_path": referral.get("ref_path", ""),
                    "inviter_id": referral.get("inviter_id"),
                },

                # ⚙️ 用户设置
                "settings": {
                    "lang": settings.get("lang", "en-US"),
                    "theme": settings.get("theme", "light"),
                },

                # 🔒 登录信息
                "sensitive": {
                    "login_ip": sensitive.get("login_ip"),
                    "last_device": (
                        sensitive.get("login_devices", [])[-1]
                        if sensitive.get("login_devices")
                        else None
                    ),
                },

                # 💡 实时在线状态（来自 Redis）
                "is_online": is_online,
                "last_seen": last_seen,
            })

        return results, total

    @staticmethod
    async def get_by_username(username: str) -> User | None:
        return await User.get(username=username, one=True)
