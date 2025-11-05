"""
# @Time    : 2025/11/4 8:34
# @Author  : Pedro
# @File    : firebase_admin_service.py
# @Software: PyCharm
"""
from firebase_admin import auth

class FirebaseAdminService:
    @staticmethod
    def create_user(email: str, password: str, display_name: str = None):
        user = auth.create_user(
            email=email,
            password=password,
            display_name=display_name,
        )
        return user

    @staticmethod
    def set_admin(uid: str, admin: bool = True):
        auth.set_custom_user_claims(uid, {"admin": admin})
