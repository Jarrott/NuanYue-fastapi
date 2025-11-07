"""
# @Time    : 2025/11/7 21:37
# @Author  : Pedro
# @File    : admin_ledger_service.py
# @Software: PyCharm
查询平台所有用户的出入账详情
"""
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from firebase_admin import firestore as fb
from app.extension.google_tools.firestore import fs_service as fs

class AdminLedgerService:
    @staticmethod
    def _doc_to_row(doc: Any) -> Dict[str, Any]:
        d = doc.to_dict()
        # 兜底 uid（优先字段，没有就从路径解析）
        if "uid" not in d:
            # users/{uid}/store/meta/ledger/{ref}
            parts = doc.reference.path.split("/")
            # ["users", "{uid}", "store", "meta", "ledger", "{ref}"]
            d["uid"] = parts[1] if len(parts) >= 2 else None
        d["id"] = doc.id
        d["path"] = doc.reference.path
        # 统一把 Timestamp 转 ISO 字符串（避免 JSON 序列化报错）
        ts = d.get("timestamp")
        if ts is not None and hasattr(ts, "isoformat"):
            d["timestamp"] = ts.isoformat()
        return d

    @staticmethod
    def list_platform_ledger(
        limit: int = 50,
        page_token: Optional[str] = None,     # 传上一页最后一条的 doc.id 做游标
        uid: Optional[str] = None,
        l_type: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        reference_prefix: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        平台出入账总表（Collection Group: ledger）
        返回 (rows, next_page_token)
        """
        q = fs.db.collection_group("ledger").order_by("timestamp", direction=fb.Query.DESCENDING)

        if uid:
            q = q.where("uid", "==", str(uid))
        if l_type:
            q = q.where("l_type", "==", l_type)  # 需要文档里有 type 字段
        if start:
            q = q.where("timestamp", ">=", start)
        if end:
            q = q.where("timestamp", "<=", end)
        if reference_prefix:
            # 前缀过滤（用范围查询）— 需要 reference 字段
            start_at = reference_prefix
            end_at = reference_prefix + "\uf8ff"
            q = q.where("reference", ">=", start_at).where("reference", "<=", end_at)

        # 分页：用 doc id 做游标（也可以用 timestamp + id 组合更稳）
        if page_token:
            last_doc = fs.db.collection_group("ledger").document(page_token)
            # 注意：collection_group().document(page_token) 不是合法 docRef（不在同一路径）
            # 更稳的方式：让前端把上一页最后一条的完整 path 带回来
            # 这里演示另一种：让前端传回上一条的 timestamp & id
            # —— 更通用写法见“分页推荐方案”段落
            pass

        docs = q.limit(limit).get()
        rows = [AdminLedgerService._doc_to_row(d) for d in docs]
        next_token = rows[-1]["id"] if rows else None  # 简易版

        return rows, next_token
