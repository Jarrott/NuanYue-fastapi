# @Time    : 2025/11/10 23:45
# @Author  : Pedro
# @File    : wallet_secure_service.py
# @Software: PyCharm
"""
🔐 Pedro-Core WalletSecureService (含管理员入口)
统一安全入账/扣款（Firestore + PostgreSQL + Redis + RTDB）
"""

import asyncio
import uuid
from decimal import Decimal
from typing import Optional
from app.extension.google_tools.fs_transaction import (
    doc, transactional, Increment, SERVER_TIMESTAMP, run_transaction
)
from app.pedro.response import PedroResponse
from app.api.cms.services.wallet.base_wallet_sync import BaseWalletSyncService


class WalletSecureService:
    """统一安全入账 / 扣款（支持管理员渠道）"""

    # ==================================================
    # 💰 通用入账接口
    # ==================================================
    @staticmethod
    async def credit_wallet(
            uid: str | int,
            amount: float | Decimal,
            reference: str,
            *,
            channel: str = "system",
            desc: str = "系统入账",
            operator_id: str = "system",
            currency: str = "USD",
            l_type: str = "credit",
            remark: Optional[str] = None
    ):
        wallet_ref = doc(f"users/{uid}/store/wallet")
        ledger_ref = doc(f"users/{uid}/store/meta/ledger/{reference}")

        delta = Decimal(str(amount))

        @transactional
        def _tx(transaction):
            existing = ledger_ref.get(transaction=transaction)
            if existing.exists:
                return {"status": "duplicate"}

            snap = wallet_ref.get(transaction=transaction)
            before = Decimal(str((snap.to_dict() or {}).get("available_balance", 0)))
            after = before + delta

            transaction.set(wallet_ref, {
                "available_balance": Increment(float(delta)),
                "updated_at": SERVER_TIMESTAMP,
                "currency": currency,
            }, merge=True)

            transaction.set(ledger_ref, {
                "uid": uid,
                "reference": reference,
                "amount": float(delta),
                "balance_before": float(before),
                "balance_after": float(after),
                "channel": channel,
                "currency": currency,
                "desc": desc,
                "l_type": l_type,
                "operator_id": operator_id,
                "remark": remark or "",
                "timestamp": SERVER_TIMESTAMP,
            })

            return {"status": "ok", "balance_after": float(after)}

        result = await asyncio.to_thread(lambda: run_transaction(_tx))

        if result.get("status") == "duplicate":
            return PedroResponse.success(msg="重复请求（已幂等处理）")

        # ✅ 全链路多源同步
        await BaseWalletSyncService.sync_all(uid, result["balance_after"])

        return PedroResponse.success(
            msg=f"入账成功 +{delta} {currency}",
            data=result
        )

    # ==================================================
    # 💸 通用扣款接口
    # ==================================================
    @staticmethod
    async def debit_wallet(
            uid: str | int,
            amount: float | Decimal,
            reference: str,
            *,
            channel: str = "system",
            desc: str = "系统扣款",
            operator_id: str = "system",
            currency: str = "USD",
            l_type: str = "debit",
            remark: Optional[str] = None
    ):
        wallet_ref = doc(f"users/{uid}/store/wallet")
        ledger_ref = doc(f"users/{uid}/store/meta/ledger/{reference}")

        dec_amount = Decimal(str(amount))

        @transactional
        def _tx(transaction):
            existing = ledger_ref.get(transaction=transaction)
            if existing.exists:
                return {"status": "duplicate"}

            snap = wallet_ref.get(transaction=transaction)
            before = Decimal(str((snap.to_dict() or {}).get("available_balance", 0)))
            if before < dec_amount:
                raise ValueError("余额不足")

            after = before - dec_amount

            transaction.set(wallet_ref, {
                "available_balance": Increment(-float(dec_amount)),
                "updated_at": SERVER_TIMESTAMP,
                "currency": currency,
            }, merge=True)

            transaction.set(ledger_ref, {
                "uid": uid,
                "reference": reference,
                "amount": float(dec_amount),
                "balance_before": float(before),
                "balance_after": float(after),
                "channel": channel,
                "currency": currency,
                "desc": desc,
                "l_type": l_type,
                "operator_id": operator_id,
                "remark": remark or "",
                "timestamp": SERVER_TIMESTAMP,
            })
            return {"status": "ok", "balance_after": float(after)}

        result = await asyncio.to_thread(lambda: run_transaction(_tx))

        if result.get("status") == "duplicate":
            return PedroResponse.success(msg="重复请求（已幂等处理）")

        # ✅ 强同步
        await BaseWalletSyncService.sync_all(uid, result["balance_after"])

        return PedroResponse.success(
            msg=f"扣款成功 -{dec_amount} {currency}",
            data=result
        )

    # ==================================================
    # 🧭 管理员入账接口（包装层）
    # ==================================================
    @staticmethod
    async def credit_wallet_admin(
            uid: str | int,
            amount: float,
            operator_id: str,
            reference: Optional[str] = None,
            remark: str = "后台入账",
            desc: str = "管理员手动入账",
            l_type: str = "admin_credit",
            currency: str = "USD",
    ):
        """
        ✅ 管理员安全入账（含全链路同步）
        Firestore + PostgreSQL + Redis + RTDB
        """
        reference = reference or f"manual_credit:{uuid.uuid4().hex[:8]}"

        result = await WalletSecureService.credit_wallet(
            uid=uid,
            amount=amount,
            reference=reference,
            channel="admin_manual",
            desc=desc,
            operator_id=operator_id,
            remark=remark,
            l_type="admin_credit"
        )

        return result

    @staticmethod
    async def debit_wallet_admin(
            uid: str | int,
            amount: float,
            operator_id: str,
            reference: Optional[str] = None,
            remark: str = "后台扣款",
            desc: str = "管理员手动扣款",
            l_type: str = "admin_debit",
    ):
        """
        ✅ 管理员安全扣款（含全链路同步）
        Firestore + PostgreSQL + Redis + RTDB
        """
        reference = reference or f"manual_debit:{uuid.uuid4().hex[:8]}"

        # 统一走通用扣款，内部已做幂等 & 多源同步
        return await WalletSecureService.debit_wallet(
            uid=uid,
            amount=amount,
            reference=reference,
            channel="admin_manual",  # 渠道固定为后台
            desc=desc,
            operator_id=operator_id,
            remark=remark,
            l_type=l_type,  # 建议用 admin_debit，便于区分运营报表
            currency="USD",
        )
