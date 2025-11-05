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


class FirebaseCreateUserSchema(BaseModel):
    email: str = None
    password: str = None
    display_name: str | None = None
    admin: bool = False  # 是否为管理员

class KYCReviewSchema(BaseModel):
    user_id: int = None
    approve: bool = None
    reason: str = None