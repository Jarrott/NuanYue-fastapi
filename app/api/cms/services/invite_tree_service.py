# @Time    : 2025/11/15 22:30
# @Author  : Pedro
# @File    : invite_tree_service.py
# @Software: PyCharm

import json
from sqlalchemy import select
from app.extension.redis.redis_client import rds
from app.api.cms.model.user import User
from app.pedro.db import async_session_factory


class InviteTreeService:

    @staticmethod
    async def get_invite_tree(uid: str):
        """
        🧬 获取邀请树（无限层级 + 带缓存）
        """

        redis = await rds.instance()
        cache_key = f"user:invite_tree:{uid}"

        # 1️⃣ Redis Cache
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)

        # 2️⃣ 查询数据库
        async with async_session_factory() as session:

            # 匹配规则必须严格：
            #   - "{uid}>%" → root 在开头（直推链）
            #   - "%>{uid}>%" → root 在中间
            #   - "%>{uid}" → root 在末尾
            stmt = select(User).where(
                User.extra["referral"]["ref_path"].astext.like(f"{uid}>%") |
                User.extra["referral"]["ref_path"].astext.like(f"%>{uid}>%") |
                User.extra["referral"]["ref_path"].astext.like(f"%>{uid}")
            )

            res = await session.execute(stmt)
            users = res.scalars().all()

        # 3️⃣ 结构化 → 识别层级
        tree = []
        for u in users:
            referral = (u.extra or {}).get("referral", {}) or {}
            ref_path = referral.get("ref_path", "")

            tree.append({
                "id": u.id,
                "nickname": getattr(u, "nickname", None),
                "level": InviteTreeService._detect_level(uid, ref_path),
                "ref_path": ref_path
            })

        # 4️⃣ 排序 → 一级 → 二级 → 三级
        tree.sort(key=lambda x: x["level"])

        result = {
            "user_id": uid,
            "total_invited": len(tree),
            "tree": tree
        }

        # 5️⃣ 缓存 1 小时
        await redis.setex(cache_key, 3600, json.dumps(result, ensure_ascii=False))

        return result


    @staticmethod
    def _detect_level(root_id: int, ref_path: str) -> int:
        """
        🎯 根据 ref_path 判断层级：
            1 → 直推
            2 → 间推
            3 → 第三级
            >3 也支持
        规则：root 所在位置之后的节点索引差值
        """

        parts = ref_path.split(">")

        if str(root_id) not in parts:
            return None

        root_index = parts.index(str(root_id))
        return len(parts) - root_index - 1   # 距离 root 的距离 = 层级
