import json
import asyncio
import traceback
from typing import Dict, Set
from fastapi import WebSocket


class WebSocketManager:
    """统一管理所有 WebSocket 连接与频道"""

    def __init__(self):
        # { channel: {WebSocket, WebSocket, ...} }
        self.channels: Dict[str, Set[WebSocket]] = {}
        # { WebSocket: {"channels": set(), "uid": str} }
        self.clients: Dict[WebSocket, dict] = {}
        # 异常统计
        self.channel_failures: Dict[str, int] = {}
        self.heartbeat_interval = 30
        self.max_failures = 5  # 某币连续失败5次则暂时跳过
        self.skip_duration = 60  # 秒数：跳过期间不推送

        # {symbol: timestamp_until_skip_end}
        self.skip_until: Dict[str, float] = {}

    # ==========================================================
    # ✅ 连接与订阅管理
    # ==========================================================
    async def connect(self, ws: WebSocket, uid: str):
        """注册连接（不在此 accept）"""
        self.clients[ws] = {"channels": set(), "uid": uid}
        print(f"✅ Client[{uid}] connected. 当前连接数: {len(self.clients)}")

    async def subscribe(self, ws: WebSocket, channel: str):
        self.channels.setdefault(channel, set())

        # ✅ 已订阅则不重复订阅
        if ws in self.channels[channel]:
            # print(f"⚠️ Client[{self.clients[ws]['uid']}] 已经订阅过 {channel}")
            return

        self.channels[channel].add(ws)
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

    # ==========================================================
    # 📢 广播 / 点对点推送
    # ==========================================================
    async def broadcast(self, channel: str, payload: dict):
        """
        向订阅该频道的客户端推送行情
        带有错误计数与容错机制
        """
        # 如果该币种在“跳过列表”中，暂不推送
        now = asyncio.get_event_loop().time()
        if channel in self.skip_until and now < self.skip_until[channel]:
            return

        receivers = self.channels.get(channel, set())
        if not receivers:
            return

        msg = json.dumps(payload, ensure_ascii=False)
        dead_ws = []

        for ws in list(receivers):
            try:
                await ws.send_text(msg)
            except Exception:
                dead_ws.append(ws)

        # 移除失效连接
        for ws in dead_ws:
            await self.disconnect(ws)

        # 记录失败次数（便于跳过）
        if dead_ws:
            self.channel_failures[channel] = self.channel_failures.get(channel, 0) + 1
            print(f"⚠️ 广播 {channel} 出现异常连接: {len(dead_ws)} 个")

            # 如果连续异常超过阈值 → 暂时跳过该币
            if self.channel_failures[channel] >= self.max_failures:
                self.skip_until[channel] = now + self.skip_duration
                self.channel_failures[channel] = 0
                print(f"🚫 {channel} 暂时跳过 {self.skip_duration}s（过多异常）")

        else:
            # 成功发送则清除异常计数
            if channel in self.channel_failures:
                self.channel_failures[channel] = 0

    async def broadcast_all(self, payload: dict):
        """广播给所有在线用户"""
        msg = json.dumps(payload, ensure_ascii=False)
        for ws in list(self.clients.keys()):
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

    # ==========================================================
    # 💓 心跳检测任务
    # ==========================================================
    async def start_heartbeat(self):
        while True:
            await asyncio.sleep(self.heartbeat_interval)
            for ws in list(self.clients.keys()):
                try:
                    await ws.send_json({"type": "ping"})
                except Exception:
                    await self.disconnect(ws)

            print(
                f"💓 Heartbeat 完成 | 在线用户: {len(self.clients)} | "
                f"频道数: {len(self.channels)} | 跳过币种: {len(self.skip_until)}"
            )


# ✅ 单例
websocket_manager = WebSocketManager()
