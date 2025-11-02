"""
# @Time    : 2025/10/30 20:25
# @Author  : Pedro
# @File    : user_wallet.py
# @Software: PyCharm
"""
from decimal import Decimal

# app/api/v1/model/user_assets.py
from sqlalchemy import Column, Integer, DECIMAL, ForeignKey, String, select, update
from app.pedro.db import Base, async_session_factory
from app.pedro.interface import InfoCrud


class UserWallets(InfoCrud):
    __tablename__ = "user_wallets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, unique=True)

    chain = Column(String(20), default="TRON")

    balance = Column(DECIMAL(38, 8), default=0)
    frozen_balance = Column(DECIMAL(38, 8), default=0)  # 提现冻结

    @classmethod
    async def add_balance(cls, user_id: int, delta: Decimal) -> Decimal:
        """
        原子累加余额：balance = balance + delta
        返回最新余额 Decimal
        """
        async with async_session_factory() as session:
            # 无钱包 -> 创建
            q = await session.execute(select(cls).where(cls.user_id == user_id))
            wallet = q.scalar_one_or_none()

            if not wallet:
                wallet = cls(user_id=user_id, balance=Decimal("0"))
                session.add(wallet)
                await session.flush()

            # ✅ 原子累加
            stmt = (
                update(cls)
                .where(cls.user_id == user_id)
                .values(balance=cls.balance + delta)
                .returning(cls.balance)
            )
            new_balance = (await session.execute(stmt)).scalar_one()

            await session.commit()
            return new_balance
