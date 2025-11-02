"""
# @Time    : 2025/10/30 20:42
# @Author  : Pedro
# @File    : admin.py
# @Software: PyCharm
"""
from pydantic import BaseModel


class AdminDepositSchema(BaseModel):
    user_id: int
    amount: float = None
    remark: str = None
    order_no: str = None

class AdminBroadcastSchema(BaseModel):
    msg: str