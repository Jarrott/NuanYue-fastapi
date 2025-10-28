# app/extension/eventbus/handlers/order_handler.py
from app.extension.eventbus import eventbus
from app.extension.websocket.wss import websocket_manager

@eventbus.on("order.completed")
async def push_order_to_user(data):
    """订单完成事件推送"""
    order_id = data["order_id"]
    user_id = data["user_id"]  # ✅ 必须有用户ID
    payload = {
        "event": "order.completed",
        "order_id": order_id,
        "user_id": user_id,
        "status": "completed"
    }
    await websocket_manager.broadcast(f"user_order:{user_id}", payload)
    print(f"📦 已通过 WS 推送给用户 {user_id}: {payload}")
