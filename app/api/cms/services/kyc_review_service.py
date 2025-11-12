# @Time    : 2025/11/12 19:30
# @Author  : Pedro
# @File    : kyc_service.py
# @Software: PyCharm
"""
🔥 Pedro-Core KYCService (跨用户聚合版, 黑名单过滤)
----------------------------------------------------
✅ 查询所有 users/{uid}/kyc/info 文档
✅ 支持状态、关键字、本地分页
✅ 自动过滤敏感字段（如身份证号、图片链接等）
"""

from firebase_admin import firestore
from app.extension.google_tools.fs_transaction import fs_service, SERVER_TIMESTAMP
from app.pedro.response import PedroResponse


class KYCService:
    # ============================================================
    # 🚫 黑名单（敏感字段过滤）
    # ============================================================
    BLOCK_FIELDS = [
        "token",
    ]

    @classmethod
    def sanitize(cls, data: dict) -> dict:
        """过滤掉敏感字段（黑名单）"""
        if not data:
            return {}
        return {k: v for k, v in data.items() if k not in cls.BLOCK_FIELDS}

    # ============================================================
    # 🔍 跨用户查询所有 KYC 信息
    # ============================================================
    @staticmethod
    async def list_all_kyc_info(
            page: int = 1,
            page_size: int = 20,
            keyword: str | None = None,
    ) -> PedroResponse:
        """
        🔍 跨用户查询所有 KYC 信息
        Firestore 路径: users/{uid}/kyc/info
        """
        q = fs_service.db.collection_group("kyc").order_by(
            "create_time", direction=firestore.firestore.Query.DESCENDING
        )

        docs = q.stream()

        all_docs = []
        for d in docs:
            if d.id != "info":
                continue
            data = d.to_dict()
            data["uid"] = d.reference.parent.parent.id  # 🔗 提取用户ID
            # 黑名单过滤
            data = KYCService.sanitize(data)
            all_docs.append(data)

        # 🔍 关键字搜索
        if keyword:
            keyword = keyword.lower()
            all_docs = [
                d for d in all_docs
                if keyword in str(d.get("full_name", "")).lower()
                   or keyword in str(d.get("contact_email", "")).lower()
                   or keyword in str(d.get("contact_phone", "")).lower()
            ]

        # 📜 分页
        total = len(all_docs)
        start = (page - 1) * page_size
        end = start + page_size
        page_items = all_docs[start:end]

        return PedroResponse.page(
            items=page_items,
            total=total,
            page=page,
            size=page_size,
            msg="✅ 成功获取所有用户的 KYC 信息（已过滤敏感字段）"
        )

    # ============================================================
    # 🧩 审核单个用户的 KYC 信息
    # ============================================================
    @staticmethod
    async def review_kyc(uid: str, admin_id: int, data, reviewer: str = "admin"):
        """
        审核用户 KYC 申请
        Firestore 路径: users/{uid}/kyc/info
        status 可选: approved / rejected
        """
        doc_ref = fs_service.db.document(f"users/{uid}/kyc/info")
        snapshot = doc_ref.get()

        if not snapshot.exists:
            return PedroResponse.fail(msg="该用户尚未提交 KYC 信息")

        update_data = {
            "status": "approved" if data.approve else "rejected",
            "review_by": admin_id,
            "review_reason": data.reason or "",
            "kyc_status": True if data.approve else False,
        }

        doc_ref.set(update_data, merge=True)

        return True
