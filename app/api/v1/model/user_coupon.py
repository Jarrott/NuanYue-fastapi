"""
# @Time    : 2025/11/10 17:56
# @Author  : Pedro
# @File    : user_coupon.py
# @Software: PyCharm
"""
from sqlalchemy import Column, BigInteger, Integer, SmallInteger, String

from app.pedro.interface import InfoCrud


class UserCoupon(InfoCrud):
    __tablename__ = "coupon"

    id = Column(Integer, primary_key=True, autoincrement=True)
    image = Column(String(255), index=True)
    name = Column(String(255), index=True)
    code = Column(String(255), index=True)
    status = Column(SmallInteger, default=0)  # 0未使用 1已使用 2已过期
