"""
# @Time    : 2025/10/30 18:56
# @Author  : Pedro
# @File    : balance_log_service.py
# @Software: PyCharm
"""
from app.api.v1.model.balance_log import BalanceLog
from app.extension.redis.redis_client import rds


class BalanceLogService:

    @staticmethod
    async def add_log(user_id: int, amount: float, tx_type: str, token="USDT", related_id=None, remark=""):
        key = f"wallet:balance:{user_id}:{token}"
        before = await rds.connection.get(key)
        before = float(before or 0)
        after = before + amount

        # ✅ 写入账本
        await BalanceLog.create(
            user_id=user_id,
            token=token,
            tx_type=tx_type,
            amount=amount,
            balance_before=before,
            balance_after=after,
            related_id=related_id,
            remark=remark
        )

        return before, after
