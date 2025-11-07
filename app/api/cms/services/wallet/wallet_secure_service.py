"""
统一的钱包安全入账服务（异步 + Firestore事务兼容）
--------------------------------------------------------
✅ 完全复用 fs_transaction 异步封装
✅ 支持: 系统入账 / 管理员入账 / 扣款 / 管理员扣款
✅ 使用 fs_transaction 提供的 SERVER_TIMESTAMP / Increment / transactional / run_transaction / doc()
✅ PostgreSQL + Redis + RTDB 同步
"""

import asyncio
import uuid
from decimal import Decimal, InvalidOperation
from typing import Optional

from app.extension.google_tools.fs_transaction import (
    db, transactional, Increment, SERVER_TIMESTAMP, run_transaction, doc
)
from app.pedro.db import async_session_factory
from app.api.cms.model.user import User
from app.pedro.response import PedroResponse
from app.extension.redis.redis_client import rds
from app.api.cms.services.wallet.wallet_sync_service import WalletSyncService


class WalletSecureService:
    # ==================================================
    # 🔧 通用工具方法
    # ==================================================
    @staticmethod
    def _safe_doc(data: dict):
        """保证 Firestore 可序列化，同时保留 Firestore 内部 sentinel 对象 (Increment, SERVER_TIMESTAMP 等)"""
        from google.cloud.firestore_v1 import SERVER_TIMESTAMP as _SERVER_TIMESTAMP
        from google.cloud.firestore_v1.transforms import Increment as _Increment
        from decimal import Decimal

        def safe(v):
            # ✅ 保留 Firestore 特殊对象
            if v is _SERVER_TIMESTAMP or isinstance(v, _Increment):
                return v
            # ✅ Decimal -> float
            if isinstance(v, Decimal):
                try:
                    return float(v)
                except Exception:
                    return str(v)
            # ✅ 普通类型直接返回
            if isinstance(v, (str, int, float, bool)) or v is None:
                return v
            # ⚠️ 其他一律转字符串
            return str(v)

        return {k: safe(v) for k, v in data.items()}

    @staticmethod
    def _coerce_amount(raw) -> Decimal:
        """
        将各种可能的金额输入安全转换为 Decimal：
        - 支持 int/float/Decimal
        - 支持 str（自动 strip）
        - 兼容 "Decimal('1')" 这类字符串
        - 兼容 "1,234.56" 含逗号
        """
        from decimal import Decimal, InvalidOperation

        if raw is None:
            raise ValueError("金额不能为空")

        # 1️⃣ 已经是 Decimal
        if isinstance(raw, Decimal):
            return raw

        # 2️⃣ 数字类型
        if isinstance(raw, (int, float)):
            return Decimal(str(raw))

        # 3️⃣ 字符串类型
        if isinstance(raw, str):
            s = raw.strip().replace(",", "")
            # 去掉可能的 "Decimal('100')" 包裹
            if s.startswith("Decimal('") and s.endswith("')"):
                s = s[len("Decimal('"):-2]
            # 防止空字符串
            if not s:
                raise ValueError(f"金额为空字符串 (raw={raw!r})")
            # 防止非法字符
            import re
            if not re.match(r"^-?\d+(\.\d+)?$", s):
                print(f"[WARN] 💥 非法金额字符串 raw={raw!r}, normalized={s!r}")
                raise ValueError(f"无效金额格式: {raw!r}")
            try:
                return Decimal(s)
            except InvalidOperation as e:
                print(f"[ERROR] 💥 Decimal 转换失败 raw={raw!r}, s={s!r}, err={e}")
                raise ValueError(f"无效金额格式: {raw!r}") from e

        # 4️⃣ 其他类型
        raise ValueError(f"不支持的金额类型: {type(raw)} ({raw!r})")

    # ==================================================
    # 💰 通用入账
    # ==================================================
    @staticmethod
    async def credit_wallet(
        uid: int | str,
        amount: float | Decimal,
        reference: str,
        *,
        l_type: str = "deposit",
        source: str = "system",
        desc: str = "系统入账",
        operator: str = "system",
        currency: str = "USD",
        remark: Optional[str] = None,
    ) -> PedroResponse:
        wallet_ref = doc(f"users/{uid}/store/wallet")
        ledger_ref = doc(f"users/{uid}/store/meta/ledger/{reference}")

        # ✅ 安全转换金额
        inc = WalletSecureService._coerce_amount(amount)

        @transactional
        def _tx(transaction):
            existing = ledger_ref.get(transaction=transaction)
            if existing.exists:
                d = existing.to_dict() or {}
                return {"status": "duplicate", "balance_after": d.get("balance_after")}

            snap = wallet_ref.get(transaction=transaction)
            before = Decimal(str((snap.to_dict() or {}).get("available_balance", 0)))
            after = before + inc

            transaction.set(
                wallet_ref,
                WalletSecureService._safe_doc({
                    "available_balance": Increment(float(inc)),
                    "updated_at": SERVER_TIMESTAMP,
                    "currency": currency,
                }),
                merge=True,
            )

            transaction.set(
                ledger_ref,
                WalletSecureService._safe_doc({
                    "uid": uid,
                    "l_type": l_type,
                    "channel": source,
                    "reference": reference,
                    "amount": float(inc),
                    "currency": currency,
                    "balance_before": float(before),
                    "balance_after": float(after),
                    "desc": desc,
                    "remark": remark or "",
                    "operator_id": operator,
                    "timestamp": SERVER_TIMESTAMP,
                }),
            )
            return {"status": "ok", "balance_after": float(after)}

        result = await asyncio.to_thread(lambda: run_transaction(_tx))

        if result.get("status") == "duplicate":
            return PedroResponse.success(msg="重复请求（已幂等处理）")

        await WalletSecureService._sync_balance(uid, result["balance_after"])
        return PedroResponse.success(
            msg=f"入账成功：+{inc} {currency}",
            data={"uid": uid, "reference": reference, "balance_after": result["balance_after"]},
        )

    # ==================================================
    # 💵 管理员手动入账
    # ==================================================
    @staticmethod
    async def credit_wallet_admin(
        uid: int | str,
        amount: float | Decimal,
        operator_id: str | int,
        *,
        l_type: str = "admin_credit",
        reference: Optional[str] = None,
        remark: Optional[str] = None,
        currency: str = "USD",
    ) -> PedroResponse:
        ref = reference or f"ADM-CR-{uuid.uuid4().hex[:12]}"
        return await WalletSecureService.credit_wallet(
            uid=uid,
            amount=amount,
            reference=ref,
            l_type=l_type,
            source="admin_manual",
            desc="管理员手动入账",
            operator=str(operator_id),
            currency=currency,
            remark=remark,
        )

    # ==================================================
    # 💸 通用扣款
    # ==================================================
    @staticmethod
    async def debit_wallet(
        uid: int | str,
        amount: float | Decimal,
        reference: str,
        *,
        l_type: str = "withdrawal",
        source: str = "system",
        desc: str = "系统扣款",
        operator: str = "system",
        currency: str = "USD",
        remark: Optional[str] = None,
    ) -> PedroResponse:
        wallet_ref = doc(f"users/{uid}/store/wallet")
        ledger_ref = doc(f"users/{uid}/store/meta/ledger/{reference}")

        # ✅ 安全转换金额
        dec_amount = WalletSecureService._coerce_amount(amount)

        @transactional
        def _tx(transaction):
            existing = ledger_ref.get(transaction=transaction)
            if existing.exists:
                d = existing.to_dict() or {}
                return {"status": "duplicate", "balance_after": d.get("balance_after")}

            snap = wallet_ref.get(transaction=transaction)
            if not snap.exists:
                raise ValueError(f"用户{uid}钱包不存在")

            before = Decimal(str((snap.to_dict() or {}).get("available_balance", 0)))
            if before < dec_amount:
                raise ValueError("余额不足")

            after = before - dec_amount

            transaction.set(
                wallet_ref,
                WalletSecureService._safe_doc({
                    "available_balance": Increment(-float(dec_amount)),
                    "updated_at": SERVER_TIMESTAMP,
                    "currency": currency,
                }),
                merge=True,
            )

            transaction.set(
                ledger_ref,
                WalletSecureService._safe_doc({
                    "uid": uid,
                    "l_type": l_type,
                    "channel": source,
                    "reference": reference,
                    "amount": float(dec_amount),
                    "currency": currency,
                    "balance_before": float(before),
                    "balance_after": float(after),
                    "desc": desc,
                    "remark": remark or "",
                    "operator_id": operator,
                    "timestamp": SERVER_TIMESTAMP,
                }),
            )
            return {"status": "ok", "balance_after": float(after)}

        result = await asyncio.to_thread(lambda: run_transaction(_tx))

        if result.get("status") == "duplicate":
            return PedroResponse.success(msg="重复请求（已幂等处理）")

        await WalletSecureService._sync_balance(uid, result["balance_after"])
        return PedroResponse.success(
            msg=f"扣款成功：-{dec_amount} {currency}",
            data={"uid": uid, "reference": reference, "balance_after": result["balance_after"]},
        )

    # ==================================================
    # 💸 管理员手动扣款
    # ==================================================
    @staticmethod
    async def debit_wallet_admin(
        uid: int | str,
        amount: float | Decimal,
        operator_id: str | int,
        *,
        l_type: str = "admin_withdrawal",
        reference: Optional[str] = None,
        remark: Optional[str] = None,
        currency: str = "USD",
    ) -> PedroResponse:
        ref = reference or f"ADM-DEBIT-{uuid.uuid4().hex[:12]}"
        return await WalletSecureService.debit_wallet(
            uid=uid,
            amount=amount,
            reference=ref,
            l_type=l_type,
            source="admin_manual",
            desc="管理员手动扣款",
            operator=str(operator_id),
            currency=currency,
            remark=remark,
        )

    # ==================================================
    # 🔄 PostgreSQL + Redis + RTDB 同步
    # ==================================================
    @staticmethod
    async def _sync_balance(uid: int | str, balance_after: float):
        """同步 PostgreSQL + Redis + RTDB"""
        # PostgreSQL
        try:
            async with async_session_factory() as session:
                user = await session.get(User, int(uid))
                if user:
                    extra = dict(user.extra or {})
                    extra["balance"] = balance_after
                    user.extra = extra
                    await session.commit()
        except Exception as e:
            print(f"[WARN] PostgreSQL 同步失败: {e}")

        # Redis
        try:
            r = await rds.instance()
            await r.set(f"user:{uid}:wallet:balance", balance_after)
        except Exception as e:
            print(f"[WARN] Redis 同步失败: {e}")

        # RTDB
        try:
            await WalletSyncService.sync_balance(int(uid), float(balance_after))
        except Exception as e:
            print(f"[WARN] RTDB 同步失败: {e}")
