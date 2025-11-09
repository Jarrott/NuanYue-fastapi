"""
🔁 Pedro-Core Auto Refill Service
支持：
1️⃣ Firestore 库存补货
2️⃣ PostgreSQL 状态更新
3️⃣ RTDB 用户余额扣款同步
"""
import asyncio
import time
from firebase_admin.firestore import firestore
from app.extension.google_tools.firestore import fs_service as fs
from app.extension.google_tools.rtdb import rtdb
from app.pedro.db import async_session_factory
from app.api.v1.model.virtual_order import Order
from app.pedro.response import PedroResponse
from app.extension.google_tools.fs_transaction import SERVER_TIMESTAMP


class RefillService:
    # ======================================================
    # 🔹 主入口
    # ======================================================
    @staticmethod
    async def auto_refill(merchant_id: str, product_id: int, uid: str, cost: float, refill_qty: int = 10):
        """
        一键补货逻辑：
        1. RTDB 扣除用户余额
        2. Firestore 更新库存
        3. PostgreSQL 更新 need_purchase 订单状态
        """
        try:
            # 1️⃣ RTDB 扣款（原子操作）
            balance = RefillService._deduct_balance_rtdb(uid, cost)
            if balance is None:
                return PedroResponse.error(msg="❌ 补货失败：余额不足或用户不存在")

            # 2️⃣ Firestore 更新库存（事务方式）
            new_stock = await asyncio.to_thread(
                RefillService._increase_stock_tx_sync, merchant_id, product_id, refill_qty
            )

            # 3️⃣ PostgreSQL 更新订单状态
            async with async_session_factory() as session:
                await session.execute(
                    Order.__table__.update()
                    .where(Order.product_id == product_id)
                    .where(Order.status == "need_purchase")
                    .values(status="pending", update_time=firestore.SERVER_TIMESTAMP)
                )
                await session.commit()

            return PedroResponse.success(
                data={
                    "uid": uid,
                    "new_balance": balance,
                    "new_stock": new_stock,
                    "refilled_qty": refill_qty
                },
                msg=f"✅ 补货成功，库存 +{refill_qty}，余额剩余 {balance}"
            )

        except Exception as e:
            print(f"[Auto Refill Error] {e}")
            return PedroResponse.error(msg=f"补货失败：{e}")

    # ======================================================
    # 🔹 RTDB 用户余额扣除
    # ======================================================
    @staticmethod
    def _deduct_balance_rtdb(uid: str, cost: float):
        """
        在 RTDB 中原子扣除余额。
        """
        ref = rtdb.reference(f"user_{uid}")
        snap = ref.get()

        if not snap:
            print(f"[WARN] RTDB user_{uid} 不存在")
            return None

        try:
            balance = float(snap.get("balance", 0))
            if balance < cost:
                print(f"[WARN] 用户 {uid} 余额不足")
                return None

            new_balance = round(balance - cost, 2)
            ref.update({
                "balance": str(new_balance),
                "last_update": int(time.time())
            })
            print(f"[INFO] 用户 {uid} 扣除金额 {cost}，剩余余额 {new_balance}")
            return new_balance

        except Exception as e:
            print(f"[RTDB Error] {e}")
            return None

    # ======================================================
    # 🔹 Firestore 补货库存事务
    # ======================================================
    @staticmethod
    def _increase_stock_tx_sync(merchant_id: str, product_id: int, qty: int):
        """
        Firestore 事务性补货（增加库存数量）
        """
        ref = fs.db.document(f"users/{merchant_id}/store/meta/products/{product_id}")

        @firestore.transactional
        def _tx(transaction):
            snap = ref.get(transaction=transaction)
            if not snap.exists:
                transaction.set(ref, {
                    "product_id": int(product_id),
                    "stock": qty,
                    "updated_at": SERVER_TIMESTAMP
                })
                return qty
            data = snap.to_dict() or {}
            current = int(data.get("stock", 0))
            new_stock = current + qty
            transaction.update(ref, {
                "stock": new_stock,
                "updated_at": SERVER_TIMESTAMP
            })
            return new_stock

        result = _tx(fs.db.transaction())
        print(f"[INFO] 商户 {merchant_id} 补货成功，产品 {product_id} 库存更新为 {result}")
        return result
