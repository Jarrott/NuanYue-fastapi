from decimal import Decimal

from app.api.cms.model import User
from app.api.v1.model.balance_log import BalanceLog
from app.api.v1.model.deposit import Deposit
from app.api.v1.model.user_wallet import UserWallets
from app.extension.google_tools.rtdb import rtdb
from app.extension.websocket.wss import websocket_manager
from app.pedro.exception import ParameterError
from app.pedro.manager import manager


class DepositApproveService:

    @staticmethod
    async def admin_deposit(user_id: int, amount: float, remark: str, admin_user, order_no: str = None):

        # ✅ 用统一枚举 or 转小写避免大小写问题
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
            # ✅ 管理员手工充值 -- 创建订单
            deposit = await Deposit.create(
                user_id=user_id,
                amount=amount,
                token="USDT",
                type="ADMIN_MANUAL",
                status="SUCCESS",
                remark=remark,
                operator_id=admin_user.id
            )

        # ✅ 用户钱包是否存在
        wallet = await UserWallets.get(user_id=user_id)
        if not wallet:
            wallet = await UserWallets.create(
                user_id=user_id,
                balance=0,
                commit=True
            )

        # ✅ 加余额
        if isinstance(amount, float):
            amount = Decimal(str(amount))
        await wallet.update(amount=amount, commit=True)

        # ✅ 写资金流水
        await BalanceLog.create(
            user_id=user_id,
            amount=amount,
            balance_after=wallet.balance,
            type="ADMIN_RECHARGE",
            reference_id=deposit.id,
            remark=f"管理员 {admin_user.id}: {remark}",
            commit=True
        )

        # ✅ 同步到 user.extra
        await User.update_json(user_id, "balance", Decimal(wallet.balance))

        ### ✅ 事务外通知

        await websocket_manager.send_to_user(user_id, {
            "event": "admin_recharge",
            "amount": float(amount),
            "balance": float(wallet.balance)
        })

        rtdb.push(f"user_{user_id}/audit", {
            "event": "admin_deposit",
            "amount": float(amount),
            "new_balance": float(wallet.balance),
            "order_no": getattr(deposit, "order_no", None)
        })

        return deposit
