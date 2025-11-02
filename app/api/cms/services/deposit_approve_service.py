import time
from decimal import Decimal

from app.api.cms.model import User
from app.api.v1.model.balance_log import BalanceLog
from app.api.v1.model.deposit import Deposit
from app.api.v1.model.user_wallet import UserWallets
from app.extension.google_tools.rtdb import rtdb
from app.extension.google_tools.rtdb_message import rtdb_msg
from app.extension.websocket.wss import websocket_manager
from app.pedro.exception import ParameterError
from app.pedro.manager import manager


class DepositApproveService:

    @staticmethod
    async def admin_deposit(user_id: int, amount: float, remark: str, admin_user, order_no: str = None):

        def normalize_status(s: str):
            return s.lower() if isinstance(s, str) else s

        deposit = None

        if order_no:
            deposit = await Deposit.get(order_no=order_no, user_id=user_id)

            if not deposit:
                raise ParameterError("订单不存在")

            if normalize_status(deposit.status) != "pending":
                raise ParameterError("订单已处理，不能重复审核")

            if float(deposit.amount) != float(amount):
                raise ParameterError("订单金额不匹配")

            deposit.status = "SUCCESS"

        else:
            # ✅ 管理员手工充值
            deposit = await Deposit.create(
                user_id=user_id,
                amount=amount,
                token="USDT",
                type="ADMIN_MANUAL",
                status="SUCCESS",
                remark=remark,
                operator_id=admin_user.id
            )

        # ✅ 金额 Decimal 处理
        if isinstance(amount, float):
            amt = Decimal(str(amount))
        else:
            amt = amount

        # ✅ 原子增量余额
        new_balance = await UserWallets.add_balance(user_id, amt)

        # ✅ 写资金流水
        await BalanceLog.create(
            user_id=user_id,
            amount=amt,
            balance_after=new_balance,
            type="ADMIN_RECHARGE",
            reference_id=deposit.id,
            remark=f"管理员 {admin_user.id}: {remark}",
            commit=True
        )

        # ✅ 同步到 user.extra
        await User.update_json(user_id, "balance", new_balance)

        ### ✅ 通知

        # WebSocket 实时推送
        await websocket_manager.send_to_user(user_id, {
            "event": "admin_recharge",
            "amount": float(amt),
            "balance": float(new_balance)
        })

        # Firebase 更新余额
        await rtdb_msg.update_balance(user_id, float(new_balance))

        # Firebase 审计日志
        rtdb_msg.client.push(f"user_{user_id}/audit", {
            "event": "admin_deposit",
            "amount": float(amt),
            "new_balance": float(new_balance),
            "order_no": getattr(deposit, "order_no", None),
            "time": int(time.time() * 1000)
        })

        return deposit
