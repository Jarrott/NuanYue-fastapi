# @Time    : 2025/11/10 10:30
# @Author  : Pedro
# @File    : wallet_orchestrator_service.py
# @Software: PyCharm
"""
💰 Pedro-Core Wallet Orchestrator Service
统一协调 Firestore + RTDB + Redis + Ledger 同步
--------------------------------------------------------
✅ 用于管理员手动充值/扣款/审核入账等操作
✅ 内部统一调用 WalletSecureService + WalletSyncService
✅ 自动发送 WebSocket 通知
"""

import asyncio
from app.api.cms.services.wallet.wallet_secure_service import WalletSecureService
from app.api.cms.services.wallet.wallet_sync_service import WalletSyncService
from app.extension.websocket.tasks.ws_user_notify import notify_user
from app.pedro.response import PedroResponse


class WalletOrchestratorService:

    @staticmethod
    async def handle_credit(uid: str, amount: float, reference: str,
                            operator: str = "system", desc: str = "系统入账", type_: str = "manual"):
        """
        ✅ 入账流程：
          1. 调用 WalletSecureService.credit_wallet_admin
          2. Firestore + SQL 原子入账
          3. 异步同步 RTDB/Redis
          4. 异步通知 WebSocket
        """
        result = await WalletSecureService.credit_wallet_admin(
            uid=uid,
            amount=amount,
            operator_id=operator,
            reference=reference,
            type=type_,
            remark=desc,
        )

        if not result:
            return PedroResponse.fail(msg="入账失败")

        if isinstance(result, dict) and result.get("status") == "ok":
            balance_after = float(result.get("balance_after", 0))

            # 🔄 Firestore/RTDB 同步
            asyncio.create_task(WalletSyncService.sync_balance(uid, balance_after))

            # 🔔 通知用户
            await notify_user(uid, {
                "event": "wallet_credit",
                "amount": amount,
                "msg": f"账户入账 ${amount:.2f}",
            })

            return PedroResponse.success(msg=f"充值成功：${amount:.2f} 已入账")

        return PedroResponse.fail(msg="钱包入账异常")

    @staticmethod
    async def handle_debit(uid: str, amount: float, reference: str,
                           operator: str = "system", desc: str = "系统扣款", type_: str = "manual"):
        """
        ✅ 扣款流程：
          1. 调用 WalletSecureService.debit_wallet_admin
          2. Firestore + SQL 原子扣款
          3. 异步同步 RTDB/Redis
          4. 异步通知 WebSocket
        """
        result = await WalletSecureService.debit_wallet_admin(
            uid=uid,
            amount=amount,
            operator_id=operator,
            reference=reference,
            type=type_,
            remark=desc,
        )

        if not result:
            return PedroResponse.fail(msg="扣款失败")

        if isinstance(result, dict) and result.get("status") == "ok":
            balance_after = float(result.get("balance_after", 0))

            # 🔄 同步余额
            asyncio.create_task(WalletSyncService.sync_balance(uid, balance_after))

            # 🔔 通知用户
            await notify_user(uid, {
                "event": "wallet_debit",
                "amount": amount,
                "msg": f"账户扣款 ${amount:.2f}",
            })

            return PedroResponse.success(msg=f"扣款成功：${amount:.2f}")

        return PedroResponse.fail(msg="钱包扣款异常")

    @staticmethod
    async def sync_all(uid: str):
        """
        🔄 主动全同步（Firestore → RTDB → Redis）
        """
        from app.extension.google_tools.firestore import fs_service as fs
        wallet = await fs.get(f"users/{uid}/store/wallet")
        if wallet:
            balance = float(wallet.get("available_balance", 0))
            await WalletSyncService.sync_balance(uid, balance)
            return PedroResponse.success(msg="钱包数据已强制同步")
        return PedroResponse.fail(msg="未找到钱包记录")
