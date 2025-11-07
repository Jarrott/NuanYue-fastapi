"""
# @Time    : 2025/11/6 4:05
# @Author  : Pedro
# @File    : merchant.py
# @Software: PyCharm
"""
import datetime
from typing import Optional, List, Dict
from pydantic import BaseModel, Field, EmailStr


class MerchantProfile(BaseModel):
    store_id: str
    store_name: str
    avatar: Optional[str] = None
    verify_badge: bool = False
    level: str = "bronze"
    email: EmailStr
    lang: str = "en"
    update_time: str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class WalletVO(BaseModel):
    available_balance: float = 0
    frozen_balance: float = 0
    pending_payout: float = 0
    currency: str = "USD"


class WithdrawCreate(BaseModel):
    amount: float = Field(gt=0)
    method: str = Field(default="bank")
    bank_account: Optional[str] = None


class WithdrawItem(BaseModel):
    id: str
    amount: float
    status: str
    requested_at: int


class LangPatch(BaseModel):
    lang: str = Field(pattern=r"^[a-z]{2}(-[A-Z]{2})?$")


class LogsQuery(BaseModel):
    type: Optional[str] = None
    page: int = 1
    size: int = 20


class CreateStoreSchema(BaseModel):
    address: str = None
    name: str = None
    phone: str = None
    email: EmailStr = None
    logo: str = None


class PurchaseSchema(BaseModel):
    product_id: Optional[int] = Field(None, description="单商品采购ID")
    quantity: Optional[int] = Field(None, description="单商品数量")
    items: Optional[List[Dict[str, int]]] = Field(None, description="批量采购列表",
                                                  examples=[{"product_id": 101, "quantity": 5},
                                                            {"product_id": 102, "quantity": 3}])
