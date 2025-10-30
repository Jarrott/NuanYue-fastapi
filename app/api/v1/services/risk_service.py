"""
# @Time    : 2025/10/30 19:01
# @Author  : Pedro
# @File    : risk_service.py
# @Software: PyCharm
"""
from app.extension.redis.redis_client import rds

class RiskService:

    @staticmethod
    async def evaluate_deposit(user_id: int, address: str, amount: float):
        score = 0
        flags = []

        # 黑名单
        if await RiskService.is_blacklisted(address):
            score += 100
            flags.append("blacklisted")

        # 大额检查
        if amount > 10000:
            score += 30
            flags.append("large_amount")

        # 高频充值
        # (可以缓存计数器)

        return score, flags

    @staticmethod
    async def is_blacklisted(address: str) -> bool:
        key = f"risk:blacklist:{address}"
        val = await rds.connection.get(key)
        return bool(val)
