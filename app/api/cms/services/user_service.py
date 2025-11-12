# -*- coding: utf-8 -*-
"""
# @Time    : 2025/11/12 13:05
# @Author  : Pedro
# @File    : user_service.py
# @Software: PyCharm
"""
from typing import Optional, Tuple, List
from app.api.cms.model.user import User
from app.pedro.response import PedroResponse


class UserService:
    """
    🧩 Pedro-Core 用户服务层（增强版）
    ------------------------------------------------
    ✅ 支持分页 / 搜索 / 排序
    ✅ 展开 extra 信息（balance, points, referral, settings）
    ✅ 安全过滤敏感信息（IP, 设备原始 UA）
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
        🔍 获取用户列表（包含扩展字段）
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

        # ✅ 格式化返回结果（安全展开 extra）
        results = []
        for u in users:
            extra = getattr(u, "extra", {}) or {}
            referral = extra.get("referral", {}) or {}
            settings = extra.get("settings", {}) or {}
            sensitive = extra.get("sensitive", {}) or {}

            results.append({
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "avatar": u.avatar,
                "uuid": u.uuid,
                "status": getattr(u, "status", None),
                "created_at": getattr(u, "created_at", None),
                "last_login": getattr(u, "last_login", None),

                # 🪙 扩展字段 (extra)
                "balance": extra.get("balance", 0.0),
                "phone": extra.get("phone"),
                "points": extra.get("points", 0),
                "currency": extra.get("currency", "USD"),
                "gender": extra.get("gender", None),
                "birthday": extra.get("birthday", None),
                "kyc_status": extra.get("kyc_status", 0),
                "vip_status": extra.get("vip_status", False),
                "vip_expire_at": extra.get("vip_expire_at", None),
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

                # 🔒 登录信息（过滤 raw UA）
                "sensitive": {
                    "login_ip": sensitive.get("login_ip"),
                    # "login_device_count": len(sensitive.get("login_devices", [])),
                    "last_device": (
                        sensitive.get("login_devices", [])[-1]
                        if sensitive.get("login_devices")
                        else None
                    ),
                },
            })

        return results, total

    @staticmethod
    async def get_by_username(username: str) -> User | None:
        return await User.get(username=username, one=True)
