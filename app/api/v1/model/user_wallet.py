"""
# @Time    : 2025/10/30 20:25
# @Author  : Pedro
# @File    : user_wallet.py
# @Software: PyCharm
"""
# app/api/v1/model/user_assets.py
from sqlalchemy import Column, Integer, DECIMAL, ForeignKey, String
from app.pedro.db import Base
from app.pedro.interface import InfoCrud


class UserWallets(InfoCrud):
    __tablename__ = "user_wallets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, unique=True)

    chain = Column(String(20), default="TRON")

    balance = Column(DECIMAL(38, 8), default=0)
    frozen_balance = Column(DECIMAL(38, 8), default=0)  # 提现冻结
