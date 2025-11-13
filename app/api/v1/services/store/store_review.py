# -*- coding: utf-8 -*-
"""
# @Time    : 2025/11/13 23:42
# @Author  : Pedro
# @File    : store_review_service.py
# @Software: PyCharm
"""
import time
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from firebase_admin import firestore

from app.extension.google_tools.firestore import fs_service
from app.extension.google_tools.fs_transaction import SERVER_TIMESTAMP
from app.pedro.id_helper import IDHelper
from app.pedro.response import PedroResponse


class StoreReviewService:
    """
    🛒 商家评论服务（Firestore 存储版）
    -----------------------------------------
    ✅ 用户可添加评论（每条独立文档）
    ✅ 支持商家回复 / 用户修改
    ✅ 同步更新时间
    ✅ 后续可扩展聚合平均评分
    """

    @staticmethod
    async def add_review(merchant_uid: str, user_id: str, rating: float,
                         comment: str, images: list[str] | None = None, order_id: str | None = None):
        """
        ✏️ 添加评论
        Firestore 路径: users/{merchant_uid}/store/meta/reviews/{review_id}
        """
        try:
            review_id = f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
            path = f"users/{merchant_uid}/store/meta/reviews/{review_id}"

            data = {
                "review_id": review_id,
                "merchant_id": merchant_uid,
                "user_id": user_id,
                "order_id": order_id,
                "rating": float(rating),
                "comment": comment.strip(),
                "images": images or [],
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

            await fs_service.safe_set(base=path, data=data)
            return PedroResponse.success(msg="✅ 评论已添加", data=data)

        except Exception as e:
            print(f"[ERROR] add_review failed: {e}")
            return PedroResponse.fail(msg=f"❌ 添加评论失败: {e}")

    # ------------------------------------------------------------------

    @staticmethod
    async def update_review(merchant_uid: str, review_id: str,
                            rating: float | None = None, comment: str | None = None,
                            reply: str | None = None):
        """
        🧩 更新评论内容 / 商家回复
        Firestore 路径: users/{merchant_uid}/store/meta/reviews/{review_id}
        """
        try:
            path = f"users/{merchant_uid}/store/meta/reviews/{review_id}"
            ref = fs_service.db.document(path)
            snap = ref.get()

            if not snap.exists:
                return PedroResponse.fail(msg="评论不存在")

            update_data = {"updated_at": SERVER_TIMESTAMP}

            if rating is not None:
                update_data["rating"] = float(rating)
            if comment:
                update_data["comment"] = comment.strip()
            if reply:
                update_data["reply"] = {
                    "text": reply,
                    "replied_at": SERVER_TIMESTAMP,
                }

            await fs_service.safe_update(base=path, data=update_data)
            return PedroResponse.success(msg="✅ 评论已更新", data=update_data)

        except Exception as e:
            print(f"[ERROR] update_review failed: {e}")
            return PedroResponse.fail(msg=f"❌ 更新评论失败: {e}")


    @staticmethod
    async def list_user_reviews(
        merchant_id: str,
        page: int = 1,
        size: int = 10,
        keyword: str | None = None,
    ):
        """
        👤 查看用户自己的所有评论
        Firestore 查询: collection_group("reviews").where("user_id", "==", user_id)
        """
        try:
            # ✅ 跨所有商家目录查询
            query = fs_service.db.collection_group("reviews").where("merchant_id", "==", merchant_id)

            # ✅ 拉取结果
            docs = query.stream()
            reviews = [doc.to_dict() for doc in docs if doc.exists]

            # ✅ 关键字过滤
            if keyword:
                keyword_lower = keyword.lower()
                reviews = [
                    r for r in reviews
                    if keyword_lower in str(r.get("comment", "")).lower()
                    or keyword_lower in str(r.get("reply", {}).get("text", "")).lower()
                ]

            # ✅ 按时间倒序排列
            reviews.sort(key=lambda x: x.get("created_at", ""), reverse=True)

            # ✅ 分页
            total = len(reviews)
            start = (page - 1) * size
            end = start + size
            paged = reviews[start:end]

            # ✅ 格式化输出
            formatted = []
            for r in paged:
                formatted.append({
                    "review_id": r.get("review_id"),
                    "merchant_id": r.get("merchant_id"),
                    "order_id": r.get("order_id"),
                    "rating": r.get("rating"),
                    "comment": r.get("comment"),
                    "reply": r.get("reply"),
                    "images": r.get("images", []),
                    "created_at": r.get("created_at"),
                    "updated_at": r.get("updated_at"),
                })

            return PedroResponse.page(
                items=formatted,
                total=total,
                page=page,
                size=size,
                msg="✅ 用户评论列表获取成功"
            )

        except Exception as e:
            print(f"[ERROR] list_user_reviews failed: {e}")
            return PedroResponse.fail(msg=f"❌ 查询评论失败: {e}")

    @staticmethod
    async def list_merchant_reviews(
        merchant_id: str,
        page: int = 1,
        size: int = 20,
        *,
        keyword: Optional[str] = None,
        min_rating: Optional[float] = None,
        has_image: Optional[bool] = None,
        cursor: Optional[str] = None,   # 传上次返回的 last_id，可替代 page 方案
    ) -> PedroResponse:
        """
        👑 商家查看店铺下的所有用户评论（Firestore）
        路径: users/{merchant_id}/store/meta/reviews/{review_id}

        两种分页可选：
        - 简单 page/size（小量数据）
        - 高效游标 cursor（大量数据；传上次返回的 last_id）
        """
        try:
            mid = IDHelper.safe_uid(merchant_id)
            base_col = fs_service.db.collection(f"users/{mid}/store/meta/reviews")

            # 构建查询
            q = base_col
            if min_rating is not None:
                q = q.where("rating", ">=", float(min_rating))

            if has_image is True:
                q = q.where("has_image", "==", True)
            elif has_image is False:
                q = q.where("has_image", "==", False)

            # 排序（稳定游标需要二级排序）
            # 如控制台提示需要复合索引，就按提示在 Firestore Console 创建即可
            q = (
                q.order_by("created_at", direction=firestore.firestore.Query.DESCENDING)
                 .order_by("__name__", direction=firestore.firestore.Query.DESCENDING)
            )

            # 游标分页（优先）
            if cursor:
                try:
                    snap = base_col.document(cursor).get()
                    if snap.exists:
                        q = q.start_after({
                            "created_at": snap.get("created_at"),
                            "__name__": snap.reference
                        })
                except Exception:
                    # 游标不合法时，退回不使用游标
                    pass

            q = q.limit(size)
            docs = list(q.stream())

            items: List[Dict[str, Any]] = []
            for d in docs:
                data = d.to_dict() or {}
                # 关键词过滤放客户端层，避免 Firestore 复合索引暴增
                if keyword:
                    k = keyword.lower()
                    text = f"{data.get('comment','')} {data.get('reply',{}).get('text','')}".lower()
                    if k not in text:
                        continue

                items.append({
                    "review_id": data.get("review_id") or d.id,
                    "order_id": data.get("order_id"),
                    "user_id": data.get("user_id"),
                    "user_name": data.get("user_name"),
                    "user_avatar": data.get("user_avatar"),
                    "rating": data.get("rating"),
                    "comment": data.get("comment"),
                    "images": data.get("images", []),
                    "has_image": data.get("has_image", bool(data.get("images"))),
                    "reply": data.get("reply"),  # {text, replied_at, operator}
                    "created_at": data.get("created_at"),
                    "updated_at": data.get("updated_at"),
                })

            # 简单 page/size 的总数：为避免全量扫描，这里不返回 total（或你另做统计表）
            last_id = docs[-1].id if docs else None

            return PedroResponse.success(data={
                "items": items,
                "page": page,
                "size": size,
                "cursor": last_id,  # 下次请求携带即可实现游标翻页
            }, msg="✅ 评论列表获取成功")
        except Exception as e:
            print(f"[ERROR] list_merchant_reviews failed: {e}")
            return PedroResponse.fail(msg=f"❌ 查询失败: {e}")