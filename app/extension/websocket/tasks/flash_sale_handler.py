"""
# @Time    : 2025/11/14 23:37
# @Author  : Pedro
# @File    : flash_sale_handler.py
# @Software: PyCharm
"""
from datetime import datetime, timezone

from google.cloud.firestore_v1 import FieldFilter

from app.extension.google_tools.firebase_admin_service import rtdb
from app.extension.google_tools.firestore import fs_service


async def get_current_flash_state():
    # 1️⃣ 优先读取 RTDB
    ref = rtdb.reference("flash_sale/current")
    data = ref.get()

    if data:
        return data

    # 2️⃣ Fallback 保底读取 Firestore（避免 RTDB为空）
    query = fs_service.db.collection("flash_sale") \
        .where(filter=FieldFilter("type", "==", "home_flash_sale")) \
        .where(filter=FieldFilter("status", "in", ["online", "active"])) \
        .limit(1)

    docs = query.get()

    if not docs:
        return None

    snap = docs[0].to_dict()

    return {
        "id": snap["id"],
        "status": snap["status"],
        "start_at": int(snap["start_time"].timestamp() * 1000),
        "end_at": int(snap["end_time"].timestamp() * 1000),
        # 如果没有 server_time → 使用当前服务器时间
        "server_time": int(datetime.now(timezone.utc).timestamp() * 1000)
    }

async def on_connect(websocket, uid=None):
    # 获取当前活动快照
    current_state = await get_current_flash_state()

    # 推送一次初始化倒计时数据
    await websocket.send_json({
        "event": "flash_sale_sync",
        "data": current_state
    })