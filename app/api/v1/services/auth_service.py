"""
# @Time    : 2025/10/30 10:37
# @Author  : Pedro
# @File    : auth_service.py
# @Software: PyCharm
"""
# app/services/auth_service.py
from fastapi import HTTPException
from firebase_admin import auth as firebase_auth
from app.pedro.pedro_jwt import jwt_service


class AuthService:
    @staticmethod
    async def create_tokens(user) -> dict:
        tokens = await jwt_service.create_pair(user)
        return {
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
        }

    @staticmethod
    def verify_google_token(id_token: str) -> dict:
        if not id_token:
            raise HTTPException(status_code=400, detail="缺少 id_token")
        try:
            dec = firebase_auth.verify_id_token(id_token,clock_skew_seconds=60)
            return {
                "uid": dec.get("uid"),
                "email": dec.get("email"),
                "name": dec.get("name", ""),
                "picture": dec.get("picture", ""),
            }
        except Exception as e:
            raise HTTPException(status_code=401, detail=str(e))
