import json
import asyncio
from typing import Dict, Set
from fastapi import WebSocket

class WebSocketManager:
    def __init__(self):
        # { channel: {WebSocket, WebSocket, ...} }
        self.channels: Dict[str, Set[WebSocket]] = {}
        # { WebSocket: {"channels": set(), "uid": str} }
        self.clients: Dict[WebSocket, dict] = {}
        self.heartbeat_interval = 30  # seconds

    # -------------------------------
    # ✅ 连接与订阅管理
    # -------------------------------
    async def connect(self, ws: WebSocket, uid: str):
        await ws.accept()
        self.clients[ws] = {"channels": set(), "uid": uid}
        print(f"✅ Client[{uid}] connected. 当前连接总数: {len(self.clients)}")

    async def subscribe(self, ws: WebSocket, channel: str):
        """订阅某个行情频道"""
        self.channels.setdefault(channel, set()).add(ws)
        self.clients[ws]["channels"].add(channel)
        print(f"➕ Client[{self.clients[ws]['uid']}] 订阅频道 {channel}")

    async def unsubscribe(self, ws: WebSocket, channel: str):
        if channel in self.channels:
            self.channels[channel].discard(ws)
        self.clients[ws]["channels"].discard(channel)
        print(f"➖ Client[{self.clients[ws]['uid']}] 取消订阅 {channel}")

    async def disconnect(self, ws: WebSocket):
        """断开连接"""
        info = self.clients.pop(ws, None)
        if not info:
            return
        for ch in info["channels"]:
            self.channels[ch].discard(ws)
        print(f"🧹 Client[{info['uid']}] disconnected")

    # -------------------------------
    # 📢 广播 & 点对点
    # -------------------------------
    async def broadcast(self, channel: str, payload: dict):
        receivers = self.channels.get(channel, set())
        if not receivers:
            return
        msg = json.dumps(payload)
        for ws in list(receivers):
            try:
                await ws.send_text(msg)
            except Exception:
                await self.disconnect(ws)

    async def send_to_user(self, uid: str, payload: dict):
        """通过 uid 推送给特定用户"""
        for ws, info in list(self.clients.items()):
            if info["uid"] == uid:
                try:
                    await ws.send_json(payload)
                except Exception:
                    await self.disconnect(ws)

    # -------------------------------
    # 💓 心跳检测（后台定期任务）
    # -------------------------------
    async def start_heartbeat(self):
        while True:
            await asyncio.sleep(self.heartbeat_interval)
            for ws in list(self.clients.keys()):
                try:
                    await ws.send_json({"type": "ping"})
                except Exception:
                    await self.disconnect(ws)
            print(f"💓 Heartbeat 检查完成 | 活跃连接数: {len(self.clients)}")


# ✅ 单例
websocket_manager = WebSocketManager()
