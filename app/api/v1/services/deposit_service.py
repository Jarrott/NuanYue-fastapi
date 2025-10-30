import time
from firebase_admin import db
from app.extension.google_tools.rtdb import FirebaseRTDB
from app.extension.redis.redis_client import rds
from app.api.v1.services.wallet_sync_service import WalletSyncService
from app.api.v1.model.deposit import Deposit, DepositTypeEnum, DepositStatusEnum


class DepositService:
    BASE = "deposit_orders"

    # ===========================
    # 用户提交人工充值
    # ===========================
    @staticmethod
    async def submit_manual_order(user_id: int, amount: float, token: str, proof: str):
        order_no = f"M{int(time.time())}{user_id}"

        # ✅ 写入数据库
        deposit = await Deposit.create(
            user_id=user_id,
            order_no=order_no,
            token=token,
            amount=amount,
            type=DepositTypeEnum.MANUAL,
            status=DepositStatusEnum.PENDING,
            proof=proof,
        )

        # ✅ 写入 Firebase pending 订单
        rtdb = FirebaseRTDB(DepositService.BASE)
        key = rtdb.push(f"user_{user_id}/tx_manual", {
            "order_no": order_no,
            "amount": str(amount),
            "token": token,
            "status": "pending",
            "source": "manual",
            "proof": proof,
            "time": int(time.time()),
            "db_id": deposit.id,  # ✅ DB ID 也写进去方便定位
        })

        return key, deposit

    # ===========================
    # 后台审核通过人工充值
    # ===========================
    @staticmethod
    async def approve_order(order_path: str, user_id: int, amount: float, deposit_id: int):
        # ✅ 修改数据库订单状态
        await Deposit.update(
            id=deposit_id,
            status=DepositStatusEnum.APPROVED
        )

        # ✅ 更新 Firebase 状态
        ref = db.reference(order_path)
        ref.update({
            "status": "approved",
            "approved_at": int(time.time())
        })

        # ✅ 同步余额
        await DepositService._sync_balance(user_id, amount)

        return True

    # ===========================
    # 后台拒绝人工充值
    # ===========================
    @staticmethod
    async def reject_order(order_path: str, deposit_id: int):
        # ✅ DB 更新
        await Deposit.update(
            id=deposit_id,
            status=DepositStatusEnum.REJECTED
        )

        # ✅ Firebase 更新
        ref = db.reference(order_path)
        ref.update({
            "status": "rejected",
            "rejected_at": int(time.time())
        })

        return True

    # ===========================
    # 链上充值入账
    # ===========================
    @staticmethod
    async def on_chain_deposit(user_id: int, tx_hash: str, amount: float, token="USDT", from_addr=None):
        # ✅ 反洗钱检查
        score, flags = await RiskService.evaluate_deposit(user_id, from_addr, amount)

        status = DepositStatusEnum.CONFIRMED if score < 100 else DepositStatusEnum.PENDING

        # ✅ 写入数据库
        deposit = await Deposit.create(
            user_id=user_id,
            order_no=f"C{int(time.time())}{user_id}",
            tx_hash=tx_hash,
            token=token,
            amount=amount,
            type=DepositTypeEnum.ONCHAIN,
            status=status,
            source_address=from_addr
        )

        # ✅ 写入 Firebase
        rtdb = FirebaseRTDB(DepositService.BASE)
        rtdb.push(f"user_{user_id}/tx_onchain", {
            "tx_hash": tx_hash,
            "amount": str(amount),
            "token": token,
            "status": status.value,
            "source": "chain",
            "address": from_addr,
            "time": int(time.time()),
            "db_id": deposit.id,
            "risk_score": score,
            "risk_flags": flags
        })

        # ✅ 风险高不直接加余额，等待人工审核
        if score < 100:
            await DepositService._sync_balance(user_id, amount)

        return deposit

    # ===========================
    # ✅ Redis + Firebase 热同步余额
    # ===========================
    @staticmethod
    async def _sync_balance(user_id: int, amount: float):
        key = f"wallet:balance:{user_id}:USDT"
        balance = await rds.connection.get(key)
        balance = float(balance or 0)
        new_balance = balance + float(amount)

        await rds.connection.set(key, new_balance)
        await WalletSyncService.sync_balance(user_id, usdt=new_balance)

        return new_balance
