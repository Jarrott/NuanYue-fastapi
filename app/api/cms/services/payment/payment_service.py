# @Time    : 2025/11/15
# @Author  : Pedro
# @File    : payment_service.py
# @Software: PyCharm
from app.pedro.response import PedroResponse
from app.extension.google_tools.firestore import fs_service
from firebase_admin.firestore import firestore
from app.pedro.config import get_current_settings

settings = get_current_settings()

class PaymentService:

    @staticmethod
    async def set_payment_method(order_id: str, uid: str, method: str):
        """
        🎯 设置支付方式（Stripe/PayPal/Wallet/COD）
        """

        if method not in ["stripe", "paypal", "wallet", "otc", "usdt"]:
            return PedroResponse.error("不支持的支付方式")

        ref = fs_service.db.collection("orders").document(order_id)
        snap = ref.get()

        if not snap.exists:
            return PedroResponse.error("订单不存在")

        order = snap.to_dict()
        if order.get("uid") != uid:
            return PedroResponse.error("非法访问")

        # 🔧 更新支付方式
        ref.update({
            "payment_method": method,
            "updated_at": firestore.SERVER_TIMESTAMP
        })

        return PedroResponse.ok({"order_id": order_id, "payment_method": method})

    @staticmethod
    async def pay(order_id: str, uid: str):
        ref = fs_service.db.collection("orders").document(order_id)
        snap = ref.get()

        if not snap.exists:
            return PedroResponse.error("订单不存在")

        order = snap.to_dict()
        method = order.get("payment_method")

        if not method:
            return PedroResponse.error("请先选择支付方式")

        if method == "wallet":
            # 🔥 调你现成的 WalletSecureService
            from app.api.cms.services.wallet.wallet_secure_service import WalletSecureService

            result = await WalletSecureService.debit_wallet(uid, order["amount"], order_id)
            if result.get("status") == "success":
                ref.update({"payment_status": "paid"})
                return PedroResponse.ok("钱包支付成功")

        if method == "stripe":
            # 返回 Stripe Checkout URL
            return PedroResponse.ok({"checkout_url": "xxxxx"})

        if method == "paypal":
            return PedroResponse.ok({"redirect": "paypal_link_here"})

        if method == "cod":
            ref.update({"payment_status": "pending_cod"})  # 标记为货到付款流程
            return PedroResponse.ok("已选择货到付款")

        return PedroResponse.error("未知支付方式")

    @staticmethod
    async def write_payment_settings():
        import json
        ref = fs_service.db.collection("payments").document("settings")
        ref.set(json.loads(settings.payment.settings))
        return PedroResponse.success(msg="付款方式列表初始化成功")

    @staticmethod
    async def get_payment_settings():
        """
        🔥 从 Firestore 获取配置，失败则 fallback .env
        """
        try:
            ref = fs_service.db.collection("payments").document("settings")
            snap = ref.get()
            if snap.exists:
                return snap.to_dict()
        except Exception as e:
            print(f"⚠️ Firestore读取失败，尝试使用.env配置: {e}")


    @staticmethod
    async def get_payment_methods(lang: str = "en"):
        """
        🎯 获取启用的支付方式 + 多语言映射
        """
        setting = await PaymentService.get_payment_settings()

        if not setting or not setting.get("enabled", False):
            return []

        methods = setting.get("methods", [])
        result = []

        for m in methods:
            if not m.get("enabled", True):
                continue

            name_dict = m.get("name", {})

            # 显示语言优先级：用户语言 > 中文 > 英文 > 任意 fallback
            display_name = (
                name_dict.get(lang)
                or name_dict.get("zh")
                or name_dict.get("en")
                or next(iter(name_dict.values()), "Unnamed")
            )

            result.append({
                "code": m.get("code"),
                "name": display_name,
                "icon": m.get("icon")
            })

        return result

    @staticmethod
    async def bind_payment_methods(uid:str, data):
        from app.extension.redis.redis_client import rds
        # 1️⃣ 获取系统支付方式，校验用户是否允许绑定
        available_methods = await PaymentService.get_payment_settings()

        codes = [m["code"] for m in available_methods.get("methods", []) if m.get("enabled", True)]

        if data.code not in codes:
            return PedroResponse.error("❌ 无效的支付方式或已禁用，不能绑定")

        # 2️⃣ 写入 Firestore（只存用户敏感数据，不存展示内容）
        ref = fs_service.db.collection("users").document(uid).collection("payments").document(data.code)
        ref.set({
            "code": data.code,
            "bind_info": data.bind_info,
            "enabled": True
        }, merge=True)

        # 3️⃣ 清除缓存
        redis = await rds.instance()
        await redis.delete(f"payment:user:{uid}:methods")

        return True