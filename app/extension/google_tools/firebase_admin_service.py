"""
# @Time    : 2025/10/30 7:17
# @Author  : Pedro
# @File    : firebase_admin_service.py
# @Software: PyCharm
"""
import firebase_admin
from firebase_admin import credentials, firestore, db, auth

from app.config.settings_manager import get_current_settings


# ✅ Firebase Admin 初始化（仅执行一次）
def init_firebase_admin():
    settings = get_current_settings()

    if not firebase_admin._apps:  # 防止重复初始化
        cred = credentials.Certificate(settings.google.firebase.service_account_path)

        firebase_admin.initialize_app(cred, {
            "databaseURL": settings.google.firebase.database_url  # ✅ 指定 RTDB URL
        })

        print("✅ Firebase Admin SDK 已初始化（含 Realtime DB）")

        # ✅ 返回实例对象
        return {
            "firestore": firestore.client(),
            "auth": auth,
            "rtdb": db
        }


# ======================================================
# ✅ 实例化客户端，供外部 import
# ======================================================
_clients = init_firebase_admin()
fs = _clients["firestore"]  # Firestore client 实例
fauth = _clients["auth"]  # Firebase Auth 实例
rtdb = _clients["rtdb"]  # Realtime Database 实例
