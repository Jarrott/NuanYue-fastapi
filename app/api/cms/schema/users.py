"""
# @Time    : 2025/11/12 16:24
# @Author  : Pedro
# @File    : users.py
# @Software: PyCharm
"""
from decimal import Decimal, InvalidOperation
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class InformationUpdateSchema(BaseModel):
    user_id: Optional[int] = None
    avatar: Optional[str] = None
    nickname: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    gender: Optional[int] = None
    birthday: Optional[str] = None
    points: Optional[int] = None