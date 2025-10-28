from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Union
from zoneinfo import ZoneInfo

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError
from fastapi import Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.extension.redis.redis_client import rds
from app.config.settings_manager import get_current_settings
from app.pedro.exception import UnAuthentication, Forbidden
from app.pedro.db import async_session_factory
from app.pedro.manager import manager as User, manager


# ======================================================
# 🔐 Pedro-Core JWT 统一服务（带版本号控制）
# ======================================================
class JWTService:
    """Pedro-Core JWT 服务（作用域 + Redis 撤销 + Version 强制失效）"""

    def __init__(self):
        self.settings = get_current_settings()
        self.secret = self.settings.auth.secret
        self.algorithm = "HS256"
        self.access_exp = timedelta(seconds=self.settings.auth.access_expires_in)
        self.refresh_exp = timedelta(days=self.settings.auth.refresh_expires_in)

        # ✅ 从配置中加载时区（默认 UTC）
        tz_name = getattr(self.settings.app, "timezone", "UTC")
        try:
            self.timezone = ZoneInfo(tz_name)
        except Exception:
            self.timezone = ZoneInfo("UTC")

    # ======================================================
    # 🧩 创建 Token（附带用户 version）
    # ======================================================
    async def create_pair(self, user: User) -> Dict[str, Union[str, List[str]]]:
        """根据用户身份自动生成 Access / Refresh Token"""
        now = datetime.now(self.timezone)
        scopes = ["admin"] if await user.is_admin() else ["user"]

        r = await rds.instance()
        version_key = f"user:{user.id}:version"
        version = await r.get(version_key)
        if not version:
            version = 1
            await r.set(version_key, version)

        # ✅ Payload 增加版本号 ver
        access_payload = {
            "uid": user.id,
            "ver": int(version),
            "scope": scopes,
            "iat": now,
            "exp": now + self.access_exp,
            "type": "access",
        }
        refresh_payload = {
            "uid": user.id,
            "ver": int(version),
            "scope": scopes,
            "iat": now,
            "exp": now + self.refresh_exp,
            "type": "refresh",
        }

        access_token = jwt.encode(access_payload, self.secret, algorithm=self.algorithm)
        refresh_token = jwt.encode(refresh_payload, self.secret, algorithm=self.algorithm)

        # ✅ 存入 Redis（状态 200 = 正常）
        await r.setex(f"token:{user.id}:{access_token}", int(self.access_exp.total_seconds()), "200")
        await r.setex(f"token:{user.id}:{refresh_token}", int(self.refresh_exp.total_seconds()), "200")

        return {"access_token": access_token, "refresh_token": refresh_token, "scopes": scopes}

    # ======================================================
    # 🧠 校验 Token + 版本号 + 权限范围
    # ======================================================
    async def verify(self, token: str, required_scopes: Optional[List[str]] = None) -> Dict[str, Any]:
        try:
            payload = jwt.decode(token, self.secret, algorithms=[self.algorithm])
        except ExpiredSignatureError:
            raise UnAuthentication("Token 已过期")
        except InvalidTokenError:
            raise UnAuthentication("Token 无效")

        uid = payload.get("uid")
        ver = int(payload.get("ver", 0))

        r = await rds.instance()

        # ✅ 检查 Redis 存储状态
        status_value = await r.get(f"token:{uid}:{token}")
        if status_value != "200":
            raise UnAuthentication("Token 已失效或被撤销")

        # ✅ 检查用户 version 是否匹配
        redis_ver = await r.get(f"user:{uid}:version")
        if redis_ver and int(redis_ver) != ver:
            raise UnAuthentication("Token 已失效（版本不匹配）")

        # ✅ 权限校验
        if required_scopes:
            token_scopes = set(payload.get("scope", []))
            if "admin" in token_scopes:
                return payload
            if not any(scope in token_scopes for scope in required_scopes):
                raise Forbidden(f"权限不足，需要作用域: {required_scopes}")

        return payload

    # ======================================================
    # 🔒 撤销控制
    # ======================================================
    async def revoke(self, token: str) -> Dict[str, str]:
        """撤销单个 Token"""
        try:
            payload = jwt.decode(token, self.secret, algorithms=[self.algorithm])
            uid = payload.get("uid")
        except Exception:
            raise UnAuthentication("无法解析 Token")

        r = await rds.instance()
        await r.setex(f"token:{uid}:{token}", 3600, "403")
        return {"msg": "Token 已撤销"}

    async def revoke_all(self, uid: int) -> Dict[str, str]:
        """撤销用户所有 Token（旧逻辑，遍历 keys）"""
        r = await rds.instance()
        keys = await r.keys(f"token:{uid}:*")
        for k in keys:
            await r.setex(k, 3600, "403")
        return {"msg": "用户所有 Token 已失效"}

    # ======================================================
    # 🚀 版本号控制（推荐强制登出方式）
    # ======================================================
    async def bump_version(self, uid: int) -> Dict[str, str]:
        """强制用户所有 Token 立即失效（版本号 +1）"""
        r = await rds.instance()
        new_ver = await r.incr(f"user:{uid}:version")
        return {"msg": f"用户 {uid} Token 版本号已更新为 {new_ver}，旧 Token 全部失效"}


# ======================================================
# ⚙️ FastAPI 依赖封装
# ======================================================
jwt_service = JWTService()
security_scheme = HTTPBearer(auto_error=False)


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security_scheme)) -> User:
    """获取当前用户对象"""
    if not credentials:
        raise UnAuthentication("缺少认证凭据")

    payload = await jwt_service.verify(credentials.credentials)
    uid = payload.get("uid")

    async with async_session_factory() as session:
        user = await manager.find_user(session=session, id=uid)
        if not user or user.is_deleted:
            raise UnAuthentication("用户不存在或已被停用")
        return user


async def login_required(current_user: User = Depends(get_current_user)) -> User:
    """普通用户依赖"""
    return current_user


async def admin_required(user: User = Depends(get_current_user)) -> User:
    """管理员依赖"""
    if not await user.is_admin():
        raise Forbidden("需要管理员权限")
    return user
