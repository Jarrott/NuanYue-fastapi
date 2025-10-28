"""
# @Time    : 2025/10/28 21:55
# @Author  : Pedro
# @File    : adapter_ws.py
# @Software: PyCharm
"""
# app/extension/eventbus/adapter_ws.py
import json
from app.extension.websocket.wss import websocket_manager

class WebSocketAdapter:
    async def publish(self, event_name, payload):
        data = payload["data"]
        uid = data.get("uid")
        msg = data.get("message")
        if uid and msg:
            await websocket_manager.send_to_user(uid, msg)
            print(f"📢 WS 推送用户 {uid}: {msg}")
