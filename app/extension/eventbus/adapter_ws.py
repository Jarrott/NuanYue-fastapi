"""
# @Time    : 2025/10/28 21:55
# @Author  : Pedro
# @File    : adapter_ws.py
# @Software: PyCharm
"""
# app/extension/eventbus/adapter_ws.py

import json
from app.pedro.service_manager import BaseService
from app.extension.websocket.wss import websocket_manager


class WebSocketAdapter(BaseService):
    name = "websocket"

    async def init(self):
        # 可以在这里做 ws 心跳、连接管理后面扩展
        print("✅ WebSocketAdapter 初始化完成")
        self.ready = True

    async def close(self):
        print("🛑 WebSocketAdapter 关闭")
        self.ready = False

    async def publish(self, event_name, payload):
        # 如果服务未ready，防止运行报错
        if not getattr(self, "ready", False):
            print("⚠️ WebSocketAdapter 未就绪，忽略推送")
            return

        data = payload.get("data", {})
        uid = data.get("uid")
        msg = data.get("message")

        if uid and msg:
            await websocket_manager.send_to_user(uid, msg)
            print(f"📢 WS 推送用户 {uid}: {msg}")
