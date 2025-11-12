"""
# @Time    : 2025/10/30 20:42
# @Author  : Pedro
# @File    : admin.py
# @Software: PyCharm
"""
from decimal import Decimal, InvalidOperation
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class AdminDepositSchema(BaseModel):
    user_id: int = None
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


class DevicesStatusSchema(BaseModel):
    user_id: int = None
    approve: bool = False


class ManualCreditSchema(BaseModel):
    user_id: int
    amount: Decimal
    reason: str

    @field_validator("amount", mode="before")
    @classmethod
    def validate_amount(cls, v):
        try:
            if v is None or (isinstance(v, str) and not v.strip()):
                raise ValueError("金额不能为空")
            return Decimal(str(v).strip())
        except InvalidOperation:
            raise ValueError(f"无效金额格式: {v}")


class ManualDebitSchema(BaseModel):
    """管理员手动扣款参数"""
    user_id: int = Field(..., description="用户ID")
    amount: Decimal = Field(..., gt=0, description="扣款金额，必须为正数")
    reason: str = Field(..., min_length=1, description="扣款原因")
    type: str = Field(default="admin_withdrawal", description="交易类型")
    currency: str = Field(default="USD", description="货币代码")

    @field_validator("amount", mode="before")
    @classmethod
    def validate_amount(cls, v):
        """金额格式校验与转换"""
        try:
            if isinstance(v, (int, float, Decimal)):
                return Decimal(str(v))
            if isinstance(v, str):
                return Decimal(v.strip())
        except (InvalidOperation, TypeError):
            raise ValueError("无效金额格式，必须为数字类型")
        return v


class MockCreateOrderSchema(BaseModel):
    """管理员手动扣款参数"""
    merchant_id: int = Field(..., description="商户ID")
    per_user: int = Field(..., description="每个mock下单的数量")
    user_count: int = Field(..., gt=0, description="下单用户数量")


class PushMessageSchema(BaseModel):
    data: Optional[str] = None
