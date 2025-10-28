"""
# @Time    : 2025/10/28 19:40
# @Author  : Pedro
# @File    : spider.py
# @Software: PyCharm
"""
from pydantic import BaseModel, ConfigDict
from typing import Optional

class CryptoAssetSchema(BaseModel):
    coin_id: str
    symbol: str
    name: str
    current_price: Optional[float]
    market_cap_rank: Optional[int]
    total_volume: Optional[float]
    price_change_percentage_24h: Optional[float]
    is_hot: bool
    is_trending: bool

    model_config = ConfigDict(from_attributes=True)
