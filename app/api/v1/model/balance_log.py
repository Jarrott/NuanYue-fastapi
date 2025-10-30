# app/api/v1/model/balance_log.py
from sqlalchemy import Column, Integer, DECIMAL, String, DateTime, func
from app.pedro.db import Base
from app.pedro.interface import InfoCrud


class BalanceLog(InfoCrud):
    __tablename__ = "balance_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, index=True)

    amount = Column(DECIMAL(38, 8), nullable=False)
    balance_after = Column(DECIMAL(38, 8), nullable=False)

    type = Column(String(30))  # OTC_RECHARGE / AUTO_RECHARGE / WITHDRAW / COMMISSION
    reference_id = Column(Integer, nullable=True)  # deposit.id
    remark = Column(String(255))