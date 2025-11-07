"""
💰 AdminWalletService — 后台钱包操作服务层
负责管理端人工入账、扣款、补发奖励等操作。
调用 WalletSecureService 统一事务层（异步 Firestore 版）。
"""

import uuid as _uuid
from decimal import Decimal
from app.api.cms.services.wallet.wallet_secure_service import WalletSecureService
from app.pedro.response import PedroResponse


class AdminWalletService:
    # ======================================
    # 💵 后台手动加钱（充值、补发、奖励）
    # ======================================
    @staticmethod
    async def manual_credit(
            uid: int | str,
            amount: float | Decimal,
            reason: str,
            admin_user: str | int,
            *,
            l_type: str = "admin_credit",
            currency: str = "USD",
    ) -> PedroResponse:
        """
        💰 后台手动给用户加钱
        - 自动写入 Firestore + Ledger + PostgreSQL + RTDB
        - 幂等键：manual_credit:<uuid>
        - 参数:
            uid: 用户ID
            amount: 金额（正数）
            reason: 原因（备注）
            admin_user: 操作管理员用户名或ID
        """

        reference = AdminWalletService._build_reference("manual_credit")

        try:
            result = await WalletSecureService.credit_wallet_admin(
                uid=uid,
                amount=amount,
                operator_id=admin_user,
                reference=reference,
                l_type=l_type,
                currency=currency,
                remark=reason,
            )

            # ✅ 兼容 PedroResponse.data
            result_data = result.data if hasattr(result, "data") else {}

            return PedroResponse.success(
                msg=f"✅ 已为用户 {uid} 手动充值 {amount} {currency}"
            )
        except Exception as e:
            print(f"[ERROR] AdminWalletService.manual_credit: {e}")
            return PedroResponse.fail(msg=f"❌ 入账失败: {e}")

    # ======================================
    # 💸 后台手动扣钱（人工下分/惩罚）
    # ======================================
    @staticmethod
    async def manual_debit(
            uid: int | str,
            amount: float | Decimal,
            reason: str,
            admin_user: str | int,
            *,
            l_type: str = "admin_withdrawal",
            currency: str = "USD",
    ) -> PedroResponse:
        """
        💸 后台手动扣钱
        - 自动写入 Firestore + Ledger + PostgreSQL + RTDB
        - 幂等键：manual_debit:<uuid>
        - 参数:
            uid: 用户ID
            amount: 金额（正数）
            reason: 原因（备注）
            admin_user: 操作管理员用户名或ID
        """
        reference = AdminWalletService._build_reference("manual_debit")

        try:
            result = await WalletSecureService.debit_wallet_admin(
                uid=uid,
                amount=amount,
                operator_id=str(admin_user),
                reference=reference,
                l_type=l_type,
                currency=currency,
                remark=reason,
            )

            result_data = result.data if hasattr(result, "data") else {}

            return PedroResponse.success(
                msg=f"✅ 已为用户 {uid} 扣除 {amount} {currency}",
                data={
                    "uid": uid,
                    "amount": amount,
                    "l_type": l_type,
                    "reference": reference,
                    "reason": reason,
                    "balance_after": result_data.get("balance_after"),
                    "status": "success",
                },
            )
        except Exception as e:
            print(f"[ERROR] AdminWalletService.manual_debit: {e}")
            return PedroResponse.fail(msg=f"❌ 扣款失败: {e}")

    # ======================================
    # 🧾 统一日志辅助（可扩展）
    # ======================================
    @staticmethod
    def _build_reference(prefix: str) -> str:
        try:
            code = f"{prefix}:{_uuid.uuid4().hex[:12]}"
            return code
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[ERROR] ❌ _build_reference 异常: {type(e)} -> {e}")
            raise

