"""
# @Time    : 2025/11/6 1:37
# @Author  : Pedro
# @File    : firestore.py
# @Software: PyCharm
"""
from firebase_admin import firestore
from firebase_admin.firestore import firestore as fs
from typing import Any, Dict
import datetime


class FirestoreService:
    def __init__(self):
        self._db = None

    @property
    def db(self):
        if not self._db:
            from firebase_admin import firestore
            self._db = firestore.client()
        return self._db

    def _doc(self, path: str):
        """支持 users/123/kyc/review 这种 path 自动节解析"""
        parts = path.split("/")
        doc = self.db.collection(parts[0]).document(parts[1])
        for i in range(2, len(parts), 2):
            doc = doc.collection(parts[i]).document(parts[i+1])
        return doc

    @staticmethod
    def _add_timestamps(data: Dict[str, Any], create: bool = False):
        now = fs.SERVER_TIMESTAMP
        if create:
            data.setdefault("created_at", now)
        data["updated_at"] = now
        return data

    async def set(self, path: str, data: Dict[str, Any]):
        """写入(覆盖)，自动设置创建 & 更新时间"""
        doc = self._doc(path)
        data = self._add_timestamps(data, create=True)
        return doc.set(data)

    async def update(self, path: str, data: Dict[str, Any]):
        """更新(merge)，只写入部分字段"""
        doc = self._doc(path)
        data = self._add_timestamps(data)
        return doc.set(data, merge=True)

    async def get(self, path: str):
        doc = self._doc(path)
        snap = doc.get()
        return snap.to_dict() if snap.exists else None

    async def delete(self, path: str):
        doc = self._doc(path)
        return doc.delete()

fs_service = FirestoreService()