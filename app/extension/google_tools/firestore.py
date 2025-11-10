"""
# @Time    : 2025/11/6 1:37
# @Author  : Pedro
# @File    : firestore.py
# @Software: PyCharm
"""
import asyncio
from datetime import datetime
from typing import Any, Dict
from firebase_admin import firestore
from app.extension.google_tools.firebase_admin_service import fs


class FirestoreService:
    def __init__(self):
        self._db = None

    @property
    def db(self):
        if not self._db:
            self._db = firestore.client()
        return self._db

    def _doc(self, path: str):
        """支持 users/123/kyc/review 这种 path 自动解析"""
        parts = path.split("/")
        doc = self.db.collection(parts[0]).document(parts[1])
        for i in range(2, len(parts), 2):
            doc = doc.collection(parts[i]).document(parts[i + 1])
        return doc

    @staticmethod
    def _add_timestamps(data: Dict[str, Any], create: bool = False):
        now = firestore.SERVER_TIMESTAMP
        if create:
            data.setdefault("create_time", now)
        data["update_time"] = now
        return data

    # =====================================================
    # ✅ 异步包装所有 Firestore 同步调用
    # =====================================================
    async def set(self, path: str, data: Dict[str, Any], merge: bool = False):
        """写入(覆盖/合并)，自动设置创建 & 更新时间"""
        doc = self._doc(path)
        data = self._add_timestamps(data, create=not merge)

        def _do_set():
            doc.set(data, merge=merge)

        return await asyncio.to_thread(_do_set)

    async def update(self, path: str, data: Dict[str, Any], merge: bool = True):
        """更新(默认 merge=True)，只写入部分字段"""
        doc = self._doc(path)
        data = self._add_timestamps(data)

        def _do_update():
            doc.set(data, merge=merge)

        return await asyncio.to_thread(_do_update)

    async def get(self, path: str):
        doc = self._doc(path)

        def _normalize_firestore_data(data):
            """递归转换 Firestore 中的 DatetimeWithNanoseconds"""
            from datetime import datetime

            if isinstance(data, dict):
                return {k: _normalize_firestore_data(v) for k, v in data.items()}
            elif isinstance(data, list):
                return [_normalize_firestore_data(v) for v in data]
            elif isinstance(data, datetime):
                return data.isoformat()
            else:
                return data

        def _do_get():
            snap = doc.get()
            if not snap.exists:
                return None
            data = snap.to_dict()
            return _normalize_firestore_data(data)

        return await asyncio.to_thread(_do_get)

    async def delete(self, path: str):
        doc = self._doc(path)

        def _do_delete():
            doc.delete()

        return await asyncio.to_thread(_do_delete)

    # ✅ 新增通用安全 update 方法
    async def safe_update(self, path: str, data: dict):
        """
        🔄 安全更新 Firestore 文档（自动获取 DocumentReference）
        - 如果文档不存在则创建
        - 不会抛出 'Client has no attribute update' 错误
        """
        try:
            ref = self.db.document(path)
            ref.update(data)
        except Exception as e:
            # 若文档不存在，fallback 到 set()
            if "No document to update" in str(e):
                ref.set(data)
            else:
                raise e

    # ✅ 新增通用 set 方法（防止旧版本未定义）
    async def safe_set(self, path: str, data: dict):
        """
        ⚡ 安全创建或覆盖 Firestore 文档
        """
        ref = self.db.document(path)
        ref.set(data)


# ✅ 实例化单例
fs_service = FirestoreService()
