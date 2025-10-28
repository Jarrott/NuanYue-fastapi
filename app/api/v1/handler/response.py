"""
# @Time    : 2025/10/28 5:22
# @Author  : Pedro
# @File    : response.py
# @Software: PyCharm
"""
from pydantic import BaseModel
from typing import Optional

class PedroBaseModel(BaseModel):
    code: int = 2000


class SuccessResponse(BaseModel):
    msg: str = "执行成功"
    code: int = 2002
    request: Optional[str] = None

class LoginSuccessResponse(PedroBaseModel):
    access_token: str = ""
    refresh_token: str = ""
    code: int = 2002

class HotCryptoResponse(PedroBaseModel):
    access_token: str = ""
    refresh_token: str = ""
    data: Optional[list[dict]] = {}
    code: int = 2002