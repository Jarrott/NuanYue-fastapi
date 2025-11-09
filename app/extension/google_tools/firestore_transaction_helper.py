# @Time    : 2025/11/8 02:58
# @Author  : Pedro
# @File    : firestore_transaction_helper.py
# @Software: PyCharm
"""
🔥 Firestore 事务统一封装模块（兼容 Firebase Admin 版本）
------------------------------------------------
- Firebase Admin SDK 没有 run_transaction()
- 使用 transaction() 手动管理事务上下文
- 异步封装 + 自动同步 PostgreSQL / Redis / RTDB
"""

import asyncio

from firebase_admin.firestore import firestore
from app.extension.google_tools.firestore import fs_service as fs
from app.api.cms.services.wallet.wallet_secure_service import WalletSecureService


class FirestoreTransactionHelper:
    @staticmethod
    async def run(uid: str, tx_func) -> bool:
        """
        ✅ 运行 Firestore 事务并在成功后自动同步余额
        Args:
            uid: 用户ID
            tx_func: 带 transaction 参数的函数 (def _tx(transaction))
        """
        def _run_in_thread():
            transaction = fs.db.transaction()
            # 🔹 开启 Firestore 事务上下文
            @firestore.transactional
            def _wrapped(transaction):
                return tx_func(transaction)
            return _wrapped(transaction)

        # 🔹 在线程池中执行事务
        await asyncio.to_thread(_run_in_thread)

        # 🔹 成功后读取钱包余额并同步
        try:
            wallet_ref = fs.db.document(f"users/{uid}/store/wallet")

            def _read_wallet():
                snap = wallet_ref.get()
                data = snap.to_dict() or {}
                return float(data.get("available_balance", 0))

            balance_after = await asyncio.to_thread(_read_wallet)
            await WalletSecureService._sync_balance(uid, balance_after)
            print(f"[SYNC] ✅ 用户 {uid} 余额同步成功 balance_after={balance_after}")
        except Exception as e:
            print(f"[WARN] ⚠️ 同步余额失败: {e}")

        return True
