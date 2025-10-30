"""
# @Time    : 2025/10/30 20:27
# @Author  : Pedro
# @File    : user_wallet_service.py
# @Software: PyCharm
"""
from sqlalchemy import select

# app/api/v1/services/user_assets_service.py
from app.api.v1.model.user_wallet import UserWallets

class UserAssetsService:

    @staticmethod
    async def get_or_create(session, user_id):
        assets = await session.scalar(
            select(UserWallets).where(UserWallets.user_id == user_id)
        )
        if not assets:
            assets = UserWallets(user_id=user_id)
            session.add(assets)
            await session.flush()
        return assets

    @staticmethod
    async def increase_balance(session, user_id, amount):
        assets = await UserAssetsService.get_or_create(session, user_id)
        assets.balance += amount
        return assets.balance
