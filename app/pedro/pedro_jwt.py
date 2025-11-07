from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Union
from zoneinfo import ZoneInfo
import hashlib
import jwt
from jwt import ExpiredSignatureError, InvalidTokenError
from fastapi import Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.api.v1.schema.user import UserAgentSchema
from app.extension.redis.redis_client import rds
from app.config.settings_manager import get_current_settings
from app.pedro.exception import UnAuthentication, Forbidden
from app.pedro.db import async_session_factory
from app.pedro.manager import manager as User, manager
from firebase_admin import auth


# ======================================================
# 🔐 Pedro-Core JWT 统一服务（含信任设备 + 风控 + AntiReplay）
# ======================================================
class JWTService:
    def __init__(self):
        self.settings = get_current_settings()
        self.secret = self.settings.auth.secret
        self.algorithm = "HS256"
        self.access_exp = self.settings.auth.access_timedelta
        self.refresh_exp = self.settings.auth.refresh_timedelta
        tz_name = getattr(self.settings.app, "timezone", "UTC")
        try:
            self.timezone = ZoneInfo(tz_name)
        except Exception:
            self.timezone = ZoneInfo("UTC")

    # ------------------------------------------------------
    # 🧩 Fingerprint 生成（IP + UA）
    # ------------------------------------------------------
    @staticmethod
    def make_fingerprint(user_agent: str, ip: str) -> str:
        base = f"{user_agent}|{ip}"
        return hashlib.sha256(base.encode()).hexdigest()[:32]

    # ------------------------------------------------------
    # 🧩 信任设备策略（7/30 天有效）
    # ------------------------------------------------------
    async def trust_device(self, uid: int, fingerprint: str, days: int = 30):
        r = await rds.instance()
        key = f"user:trusted:{uid}:{fingerprint}"
        await r.setex(key, days * 86400, "1")

    async def is_trusted_device(self, uid: int, fingerprint: str) -> bool:
        r = await rds.instance()
        val = await r.get(f"user:trusted:{uid}:{fingerprint}")
        return val == b"1"

    # ------------------------------------------------------
    # 🧠 登录风控：异常登录检测
    # ------------------------------------------------------
    async def check_login_risk(self, uid: int, fingerprint: str, ip: str):
        r = await rds.instance()
        key = f"user:devices:{uid}"

        raw_vals = await r.lrange(key, 0, -1)
        existing = [v.decode() if isinstance(v, bytes) else v for v in raw_vals]

        if fingerprint not in existing:
            # 新设备写入
            await r.lpush(key, fingerprint)
            await r.ltrim(key, 0, 4)  # 保留最近 5 个

            # 检查是否信任设备
            trusted = await self.is_trusted_device(uid, fingerprint)
            if not trusted:
                print(f"⚠️ 风险提示: 用户 {uid} 新设备登录, IP={ip}")
                # TODO: 发通知（邮件 / WebSocket / 管理员报警）

    async def after_login_security(self, user, request, payload):
        """统一登录后安全处理流程"""
        ip = request.client.host
        ua = request.headers.get("User-Agent", "")
        fingerprint = self.make_fingerprint(ua, ip)

        # ✅ 异常登录探测
        await self.check_login_risk(user.id, fingerprint, ip)

        # ✅ 设备记录 & 限制
        device = UserAgentSchema.from_ua(ua).model_dump()
        await user.jpush_unique_path(
            "sensitive.login_devices",
            device,
            unique_fields=["device", "browser", "os"],
            limit=2
        )

        # ✅ “记住设备”逻辑
        if getattr(payload, "remember_me", False):
            await self.trust_device(user.id, fingerprint, days=30)

        # ✅ 最后才生成 Token（避免风控冲突）
        tokens = await self.create_pair(user)
        return tokens

    # ------------------------------------------------------
    # 🧩 Anti-Replay 防重放：记录使用过的 Token
    # ------------------------------------------------------
    async def check_replay(self, uid: int, token: str) -> None:
        r = await rds.instance()
        key = f"token:used:{uid}:{token}"
        if await r.exists(key):
            raise UnAuthentication("Token 已被使用，请重新登录")
        await r.setex(key, int(self.access_exp.total_seconds()), "1")

    # ======================================================
    # 🧩 创建 Token（含 version + fingerprint）
    # ======================================================
    async def create_pair(self, user: User) -> Dict[str, Union[str, List[str]]]:
        """根据用户身份自动生成 Access / Refresh Token（最多 2 个在线）"""
        now = datetime.now(self.timezone)
        scopes = ["admin"] if await user.is_admin() else ["user"]

        # ✅ 检查用户是否启用设备锁
        require_lock = getattr(user.extra, "device_lock", False)
        fp = None

        if require_lock:
            request = self.settings.current_request  # 自动从中间件注入
            ua = request.headers.get("User-Agent", "")
            ip = request.client.host
            fp = self.make_fingerprint(ua, ip)

        r = await rds.instance()
        version_key = f"user:{user.id}:version"
        version = await r.get(version_key)
        if not version:
            version = 1
            await r.set(version_key, version)

        # ✅ 生成 Access / Refresh Token
        access_payload = {
            "uid": user.id,
            "ver": int(version),
            "scope": scopes,
            "iat": now,
            "fp": fp,
            "exp": now + self.access_exp,
            "type": "access",
        }
        refresh_payload = {
            "uid": user.id,
            "ver": int(version),
            "scope": scopes,
            "iat": now,
            "fp": fp,
            "exp": now + self.refresh_exp,
            "type": "refresh",
        }

        access_token = jwt.encode(access_payload, self.secret, algorithm=self.algorithm)
        refresh_token = jwt.encode(refresh_payload, self.secret, algorithm=self.algorithm)

        # ✅ Redis Key 模式
        access_key = f"token:{user.id}:access:{access_token}"
        refresh_key = f"token:{user.id}:refresh:{refresh_token}"

        # ✅ 检查现有 token 数量
        access_keys = await r.keys(f"token:{user.id}:access:*")

        if len(access_keys) >= 2:
            tokens_with_ttl = []
            for key in access_keys:
                ttl = await r.ttl(key)
                tokens_with_ttl.append((key, ttl if ttl > 0 else 0))

            # 按 TTL 从低到高排序 → 清掉最老的设备
            tokens_with_ttl.sort(key=lambda x: x[1])
            old_key = tokens_with_ttl[0][0]
            await r.delete(old_key)
            print(f"🧹 已清理旧 access token：{old_key}")

        # ✅ 存入 Redis（200 = 有效）
        await r.setex(access_key, int(self.access_exp.total_seconds()), "200")
        await r.setex(refresh_key, int(self.refresh_exp.total_seconds()), "200")

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "scopes": scopes,
        }

    # ------------------------------------------------------
    # 🧩 生成新的 Token
    # ------------------------------------------------------
    async def verify_refresh_token(self, refresh_token: str) -> dict:
        """刷新 Access / Refresh Token（支持 Rotation / 多设备）"""

        try:
            payload = jwt.decode(
                refresh_token,
                self.secret,
                algorithms=[self.algorithm]
            )
        except Exception:
            raise UnAuthentication("Refresh Token 无效")

        # 1️⃣ 必须是 refresh token
        if payload.get("type") != "refresh":
            raise UnAuthentication("Token 类型错误")

        uid = payload.get("uid")
        version = payload.get("ver")

        if not uid or not version:
            raise UnAuthentication("Token 无效")

        # 2️⃣ 检查用户
        user = await manager.user_model.get(id=uid)
        if not user:
            raise UnAuthentication("用户不存在")

        # 3️⃣ 检查 Redis 令牌是否还有效（防止伪造）
        r = await rds.instance()
        redis_key = f"token:{uid}:refresh:{refresh_token}"
        exists = await r.get(redis_key)
        if not exists:
            raise UnAuthentication("Refresh Token 已失效，请重新登录")

        # 4️⃣ 检查 Token 版本是否一致（后台强制下线机制）
        redis_version = await r.get(f"user:{uid}:version")
        if str(redis_version) != str(version):
            raise UnAuthentication("登录状态已变更，请重新登录")

        # ✅ 生成新的 access/refresh（Rotation 新策略）
        new = await self.create_pair(user)

        # 🧹 删除旧 Refresh Token（Token Rotation 安全策略）
        await r.delete(redis_key)

        return new

    # ======================================================
    # 🧠 校验 Token + 版本号 + 风控（不改变已有签名）
    # ======================================================
    async def verify(
            self,
            token: str,
            required_scopes: Optional[List[str]] = None,
            **kwargs  # ✅ 兼容 request 而不改变原有函数签名
    ) -> Dict[str, Any]:
        """
        校验 Token + 版本号 + 权限范围
        request 会通过 kwargs 注入：request=xxx
        """
        request = kwargs.get("request")  # ✅ 若调用方传了 request，就能拿到

        try:
            payload = jwt.decode(token, self.secret, algorithms=[self.algorithm])
        except ExpiredSignatureError:
            raise UnAuthentication("Token 已过期")
        except InvalidTokenError:
            raise UnAuthentication("Token 无效")

        uid = payload.get("uid")
        ver = int(payload.get("ver", 0))

        r = await rds.instance()

        # ✅ 兼容 access / refresh 前缀查找
        access_key = f"token:{uid}:access:{token}"
        refresh_key = f"token:{uid}:refresh:{token}"

        status_value = await r.get(access_key)
        if not status_value:
            status_value = await r.get(refresh_key)

        if status_value != "200":
            raise UnAuthentication("Token 已失效或被撤销")

        # ✅ 版本号校验
        redis_ver = await r.get(f"user:{uid}:version")
        if redis_ver and int(redis_ver) != ver:
            raise UnAuthentication("Token 已失效（版本不匹配）")

        # ✅ 用户是否要求设备锁
        # ✅ 读取设备锁开关
        raw = await r.get(f"user:{uid}:device_lock")
        require_lock = raw == b"1"

        if require_lock:
            token_fp = payload.get("fp")
            ua = request.headers.get("User-Agent", "")
            ip = request.client.host
            current_fp = self.make_fingerprint(ua, ip)

            if token_fp != current_fp:
                raise UnAuthentication("⚠️ 设备变更，需要验证设备")

        if require_lock:
            token_fp = payload.get("fp")
            ua = request.headers.get("User-Agent", "")
            ip = request.client.host
            current_fp = self.make_fingerprint(ua, ip)

            if token_fp != current_fp:
                raise UnAuthentication("⚠️ 设备变更，需要验证设备")

        # ✅（可选）风控：若传 request，检测 IP/UA 变化
        if request:
            ip = request.client.host
            ua = request.headers.get("User-Agent", "")
            fingerprint = self.make_fingerprint(ua, ip)

            # 调用登录风控（不会报错，只做通知）
            try:
                await self.check_login_risk(uid, fingerprint, ip)
            except Exception as e:
                print("⚠️ 登录风控检测异常: ", e)

        # ✅ 权限校验
        if required_scopes:
            token_scopes = set(payload.get("scope", []))
            if "admin" not in token_scopes and not any(s in token_scopes for s in required_scopes):
                raise Forbidden(f"权限不足，需要作用域: {required_scopes}")

        return payload

    # ======================================================
    # 🔒 撤销控制
    # ======================================================
    async def revoke(self, token: str) -> Dict[str, str]:
        try:
            payload = jwt.decode(token, self.secret, algorithms=[self.algorithm])
            uid = payload.get("uid")
        except Exception:
            raise UnAuthentication("无法解析 Token")

        r = await rds.instance()
        await r.setex(f"token:{uid}:{token}", 3600, "403")
        return {"msg": "Token 已撤销"}

    async def revoke_all(self, uid: int) -> Dict[str, str]:
        r = await rds.instance()
        keys = await r.keys(f"token:{uid}:*")
        for k in keys:
            await r.setex(k, 3600, "403")
        return {"msg": "用户所有 Token 已失效"}

    # ======================================================
    # 🚀 版本号控制（强制登出）
    # ======================================================
    async def bump_version(self, uid: int) -> Dict[str, str]:
        r = await rds.instance()
        new_ver = await r.incr(f"user:{uid}:version")
        return {"msg": f"用户 {uid} Token 版本号已更新为 {new_ver}，旧 Token 全部失效"}


# ======================================================
# ⚙️ FastAPI 依赖封装
# ======================================================
jwt_service = JWTService()
security_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
        request: Request = None
) -> User:
    if not credentials:
        raise UnAuthentication("缺少认证凭据")

    # ✅ 传 request 但 verify 参数不变
    payload = await jwt_service.verify(credentials.credentials, request=request)

    uid = payload.get("uid")

    async with async_session_factory() as session:
        user = await manager.find_user(session=session, id=uid)
        if not user or user.is_deleted:
            raise UnAuthentication("用户不存在或已被停用")
        return user


async def login_required(current_user: User = Depends(get_current_user)) -> User:
    return current_user


async def admin_required(user: User = Depends(get_current_user)) -> User:
    if not await user.is_admin():
        raise Forbidden("需要管理员权限")
    return user


class FirebaseAuthService:

    @staticmethod
    async def create_custom_token(user_id: int):
        # 👇 这里可以放自定义用户字段
        additional_claims = {
            "uid": str(user_id)
        }
        token = auth.create_custom_token(str(user_id), additional_claims)
        return token.decode("utf-8")
