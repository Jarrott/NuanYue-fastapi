"""
# @Time    : 2025/10/28 22:57
# @Author  : Pedro
# @File    : order.py
# @Software: PyCharm
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, func
from app.pedro.interface import InfoCrud

class Order(InfoCrud):
    __tablename__ = "virtual_orders"


    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(256), nullable=False)
    product_id = Column(Integer, nullable=False)
    amount = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String(32), default="pending")
