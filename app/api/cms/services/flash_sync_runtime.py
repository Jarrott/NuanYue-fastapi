from datetime import datetime, timezone

from app.extension.google_tools.firebase_admin_service import rtdb
from app.extension.google_tools.fs_transaction import db

now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)


class FlashSyncRuntime:

    @staticmethod
    async def on_start(event_id, end_time:datetime):
        flash_end_time = int(end_time.timestamp() * 1000)

        # 1. Firestore 更新
        db.collection("flash_sale").document(event_id).update({
            "status": "active",
            "activated_at": datetime.now(timezone.utc),  # 可选记录
        })
        try:
        # 2. RTDB 更新
            await  rtdb.reference("flash_sale/current").set({
                "status": "active",
                "flash_end_time": flash_end_time,
                "server_time": now_ms
            })
        except Exception as e:
            raise e

        # 3. WebSocket 推送
        from app.extension.websocket.tasks.ws_user_notify import notify_broadcast

        await notify_broadcast({"event": "flash_sale_start", "id": event_id, "server_time": now_ms})

    @staticmethod
    async def on_end(event_id: str):
        from app.extension.websocket.tasks.ws_user_notify import notify_broadcast

        # 1️⃣ 更新 Firestore 状态
        db.collection("flash_sale") \
            .document(event_id) \
            .update({
            "status": "ended",
            "ended_at": datetime.now(timezone.utc)
        })

        # 2️⃣ 获取 Firestore数据（用于 RTDB覆盖写）
        snap = db.collection("flash_sale").document(event_id).get()
        data = snap.to_dict()
        print(data["end_time"])

        # 3️⃣ RTDB 写完整结构（🔥 不只写 status）
        rtdb.reference("flash_sale/current").update({
            "status": "ended",
            "server_time": now_ms,
            "end_at": int(data["end_time"].timestamp() * 1000),
            "id": data["id"]
        })

        # 4️⃣ WebSocket 推送事件广播
        await notify_broadcast({
            "event": "flash_sale_end",
            "id": event_id,
            "server_time": now_ms
        })
