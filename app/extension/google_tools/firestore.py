# -*- coding: utf-8 -*-
"""
# @Time    : 2025/11/13 23:59
# @Author  : Pedro
# @File    : firestore.py
# @Software: PyCharm
"""
import asyncio
from datetime import datetime
from typing import Any, Dict
from firebase_admin import firestore
from app.extension.google_tools.firebase_admin_service import fs

# ✅ 引入统一 ID 解析工具
from app.pedro.id_helper import IDHelper


class FirestoreService:
    def __init__(self):
        self._db = None

    @property
    def db(self):
        if not self._db:
            self._db = firestore.client()
        return self._db

    # =====================================================
    # 🧩 路径解析（自动识别 user / id / uuid）
    # =====================================================
    def _resolve_path(self, base: Any, subpath: str | None = None) -> str:
        """
        ✅ 自动识别各种 uid 形式并返回 Firestore 路径
        支持：
            - fs_service.get("users/15/store/profile")
            - fs_service.get(user, "store/profile")
            - fs_service.get(user.uuid, "store/profile")
            - fs_service.get(12345, "store/profile")
        """
        # 传入完整路径 → 直接返回
        if isinstance(base, str) and "/" in base and not subpath:
            return base

        # user 对象 / uuid / id
        uid = IDHelper.safe_uid(base)
        subpath = subpath.strip("/") if subpath else ""
        return f"users/{uid}/{subpath}" if subpath else f"users/{uid}"

    # =====================================================
    # 🔧 路径 → DocumentReference
    # =====================================================
    def _doc(self, path: str):
        """支持 users/123/kyc/review 这种 path 自动解析"""
        parts = path.split("/")
        doc = self.db.collection(parts[0]).document(parts[1])
        for i in range(2, len(parts), 2):
            doc = doc.collection(parts[i]).document(parts[i + 1])
        return doc

    # =====================================================
    # 🕓 自动时间戳管理
    # =====================================================
    @staticmethod
    def _add_timestamps(data: Dict[str, Any], create: bool = False):
        now = firestore.firestore.SERVER_TIMESTAMP
        if create:
            data.setdefault("updated_at", now)
        data["updated_at"] = now
        return data

    # =====================================================
    # ✅ 写入 (支持 user / id / path)
    # =====================================================
    async def set(self, base: Any, data: Dict[str, Any], subpath: str | None = None, merge: bool = False):
        path = self._resolve_path(base, subpath)
        doc = self._doc(path)
        data = self._add_timestamps(data, create=not merge)

        def _do_set():
            doc.set(data, merge=merge)

        return await asyncio.to_thread(_do_set)

    # =====================================================
    # ✅ 更新 (merge=True)
    # =====================================================
    async def update(self, base: Any, data: Dict[str, Any], subpath: str | None = None, merge: bool = True):
        path = self._resolve_path(base, subpath)
        doc = self._doc(path)
        data = self._add_timestamps(data)

        def _do_update():
            doc.set(data, merge=merge)

        return await asyncio.to_thread(_do_update)

    # =====================================================
    # ✅ 获取 (支持 user / id / uuid)
    # =====================================================
    async def get(self, base: Any, subpath: str | None = None):
        path = self._resolve_path(base, subpath)
        doc = self._doc(path)

        def _normalize_firestore_data(data):
            """递归转换 Firestore 中的 DatetimeWithNanoseconds"""
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
            return _normalize_firestore_data(snap.to_dict())

        return await asyncio.to_thread(_do_get)

    # =====================================================
    # ✅ 删除文档
    # =====================================================
    async def delete(self, base: Any, subpath: str | None = None):
        path = self._resolve_path(base, subpath)
        doc = self._doc(path)

        def _do_delete():
            doc.delete()

        return await asyncio.to_thread(_do_delete)

    # =====================================================
    # ✅ 安全更新 (若不存在自动 set)
    # =====================================================
    async def safe_update(self, base: Any, data: dict, subpath: str | None = None):
        path = self._resolve_path(base, subpath)
        ref = self.db.document(path)
        try:
            ref.update(data)
        except Exception as e:
            if "No document to update" in str(e):
                ref.set(data)
            else:
                raise e

    # =====================================================
    # ✅ 安全 set
    # =====================================================
    async def safe_set(
            self,
            path: str = None,
            base: str = None,
            data: dict = None,
            subpath: str | None = None,
            merge: bool = True,
    ):
        """
        ⚡ 安全写入 Firestore
        - 支持直接传 path
        - 支持 base + subpath 拼接
        - 自动附加 SERVER_TIMESTAMP
        - 自动 merge
        """
        # 🧩 支持直接 path 模式
        if path:
            resolved_path = path
        else:
            # 🧩 兼容旧写法：base + subpath 模式
            if not base:
                raise ValueError("safe_set() requires either 'path' or 'base'")
            resolved_path = self._resolve_path(base, subpath)

        # ✅ 路径检查（偶数层）
        parts = [p for p in resolved_path.split("/") if p]
        if len(parts) % 2 != 0:
            raise ValueError(
                f"Invalid Firestore path '{resolved_path}': must have even segments (collection/doc/...)"
            )

        # ✅ 自动时间戳
        from firebase_admin import firestore
        now = firestore.firestore.SERVER_TIMESTAMP
        data = data or {}
        data.setdefault("create_time", now)
        data["update_time"] = now

        # ✅ 写入
        ref = self.db.document(resolved_path)
        ref.set(data, merge=merge)

        print(f"✅ [FirestoreService.safe_set] path={resolved_path}")

    # =====================================================
    # ✅ 批量读取
    # =====================================================
    async def get_multi(self, paths: list[str]):
        async def fetch(path):
            ref = self.db.document(path)
            snap = await asyncio.get_event_loop().run_in_executor(None, ref.get)
            return path.split("/")[-1], snap.exists

        results = await asyncio.gather(*(fetch(p) for p in paths))
        return {pid: exists for pid, exists in results}

    # =====================================================
    # ✅ 列出集合文档
    # =====================================================
    async def list_documents(self, collection_path: str):
        loop = asyncio.get_event_loop()
        collection_ref = self.db.collection(collection_path)
        docs = await loop.run_in_executor(None, lambda: list(collection_ref.stream()))
        return [doc for doc in docs if doc.exists]


# ✅ 单例实例
fs_service = FirestoreService()
