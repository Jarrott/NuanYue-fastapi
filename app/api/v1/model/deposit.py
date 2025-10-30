# app/api/cms/model/deposit.py

from sqlalchemy import Column, Integer, BigInteger, String, DECIMAL, Enum, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.pedro.interface import InfoCrud


class DepositTypeEnum(str, Enum):
    ONCHAIN = 'onchain'
    MANUAL = "manual"
    USDT = "usdt"


class DepositStatusEnum(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"  # 链上确认
    APPROVED = "approved"  # 人工充值审核通过
    REJECTED = "rejected"


class Deposit(InfoCrud):
    __tablename__ = "deposit"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("user.id"))
    order_no = Column(String(64), unique=True, index=True)
    tx_hash = Column(String(128), index=True, nullable=True)
    chain = Column(String(32), default="TRON")
    token = Column(String(16), default="USDT")
    amount = Column(DECIMAL(38, 8), nullable=False)
    type = Column(
        String(20),
        default=DepositTypeEnum.USDT
    )
    status = Column(
        String(20),
        default=DepositStatusEnum.PENDING
    )
    proof = Column(Text, nullable=True)
    source_address = Column(String(128), nullable=True)
