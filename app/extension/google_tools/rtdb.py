"""
# @Time    : 2025/10/30 18:39
# @Author  : Pedro
# @File    : rtdb.py
# @Software: PyCharm
"""
from typing import Any, Callable, Optional
from firebase_admin import db
import logging
import threading
from app.extension.google_tools.firebase_admin_service import *


class FirebaseRTDB:
    """
    Firebase Realtime Database 封装
    支持 CRUD + push + path builder
    """

    def __init__(self, base: str = ""):
        self.base = base.rstrip("/")

    def path(self, *args) -> str:
        parts = [self.base] + list(args)
        return "/".join(
            str(p).strip("/") for p in parts if p is not None and p != ""
        )

    # ---------- CRUD ----------
    def set(self, path: str, data: Any):
        db.reference(path).set(data)

    def update(self, path: str, data: dict):
        db.reference(path).update(data)

    def get(self, path: str) -> Any:
        return db.reference(path).get()

    def push(self, path: str, data: Any) -> str:
        ref = db.reference(path).push()
        ref.set(data)
        return ref.key  # 返回自动ID

    def delete(self, path: str):
        db.reference(path).delete()

    # ---------- LISTENER (可选) ----------
    def listen(self, path: str, callback: Callable[[Any], None]):
        """
        后台线程监听（开发/调试用）
        * 回调callback(snapshot_dict)
        """
        ref = db.reference(path)

        def _listener(event):
            callback({
                "event": event.event_type,
                "path": event.path,
                "data": event.data
            })

        thread = threading.Thread(
            target=ref.listen,
            args=(_listener,),
            daemon=True
        )
        thread.start()

rtdb = FirebaseRTDB()