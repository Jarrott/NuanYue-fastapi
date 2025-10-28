"""
# @Time    : 2025/10/28 19:43
# @Author  : Pedro
# @File    : binance.py
# @Software: PyCharm
"""
import asyncio
import json
import ssl
import time
import traceback
import websockets
from typing import List
from redis import asyncio as aioredis

from app.api.v1.model.crypto_assets import CryptoAsset
from app.pedro.config import get_current_settings
from app.extension.websocket.wss import websocket_manager

# =========================================================
# Redis Key 模板
# =========================================================
REDIS_LAST_KEY = "market:last_push:{symbol}:{interval}"
REDIS_SNAPSHOT = "market:snapshot:{symbol}:{interval}"
STREAM_HEARTBEAT = {}

settings = get_current_settings()


# =========================================================
# Binance 单币监听器
# =========================================================
class BinanceKlineStream:
    """异步监听单币种实时 K线"""

    def __init__(self, symbol: str, interval: str, redis: aioredis.Redis):
        self.symbol = symbol.lower()
        self.interval = interval
        self.redis = redis
        self.url = f"wss://stream.binance.com:9443/ws/{self.symbol}@kline_{self.interval}"
        self.last_emit_ts = 0
        self.coalesce_ms = 800  # 聚合时间阈值（防止高频推送）

    async def connect(self):
        """主循环：保持长连，自动重连"""
        backoff = 1
        while True:
            try:
                async with websockets.connect(self.url, ssl=ssl.SSLContext()) as ws:
                    STREAM_HEARTBEAT[f"{self.symbol}-{self.interval}"] = time.strftime("%H:%M:%S")
                    # print(f"🔌 [{self.symbol}-{self.interval}] 已连接 Binance Stream")
                    while True:
                        msg = await ws.recv()
                        await self.handle_message(msg)
            except Exception as e:
                print(f"⚠️ [{self.symbol}-{self.interval}] 连接断开，重试中: {e}")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    async def handle_message(self, msg: str):
        """处理实时 K线消息"""
        try:
            data = json.loads(msg)
            if data.get("e") != "kline":
                return

            k = data["k"]
            symbol = k["s"].upper()
            interval = k["i"]
            channel = f"{symbol.lower()}-{interval}"  # ✅ 统一频道命名
            now_ms = int(time.time() * 1000)

            payload = {
                "symbol": symbol,
                "interval": interval,
                "open": k["o"],
                "high": k["h"],
                "low": k["l"],
                "close": k["c"],
                "volume": k["v"],
                "trades": k["n"],
                "timestamp": k["t"],
                "closed": k["x"],
            }

            # ✅ 缓存最新 K线
            await self.redis.set(
                REDIS_SNAPSHOT.format(symbol=symbol, interval=interval),
                json.dumps(payload),
                ex=600,
            )
            await self.redis.set(
                REDIS_LAST_KEY.format(symbol=symbol, interval=interval),
                now_ms,
                ex=600,
            )

            # ✅ 限流：避免频繁广播
            if not k["x"] and (now_ms - self.last_emit_ts < self.coalesce_ms):
                return
            self.last_emit_ts = now_ms

            # ✅ 推送至 WebSocket 频道
            await websocket_manager.broadcast(
                f"{symbol.lower()}-{interval}",
                {
                    "type": "ticker",  # ✅ 前端监听字段
                    "symbol": symbol.upper(),
                    "close": k["c"],
                    "volume": k["v"],
                    "interval": interval
                }
            )

            # ✅ 打印调试
            # print(f"📤 推送频道 {channel} | 收盘价 {k['c']} | 成交量 {k['v']}")

        except Exception as e:
            print(f"⚠️ [{self.symbol}] 解析异常: {e}")
            traceback.print_exc()

        await websocket_manager.broadcast_all(
            {
                "type": "ticker",
                "symbol": symbol.upper(),
                "close": k["c"],
                "volume": k["v"],
                "interval": interval
            }
        )


# =========================================================
# Binance 多币监听管理器
# =========================================================
class KlineHub:
    """多币种统一监听管理"""

    def __init__(self, pairs: List[List[str]]):
        self.pairs = pairs
        self.redis = None
        self.tasks = []

    async def start(self):
        """初始化 Redis 并启动所有监听任务"""
        self.redis = await aioredis.from_url(
            settings.redis.redis_url, decode_responses=True
        )
        total = sum(len(i[1]) for i in self.pairs)
        print(f"🌐 [Binance] 正在启动 {total} 条实时行情流 ...")
        start_time = time.time()

        connected = 0
        for symbol, intervals in self.pairs:
            for itv in intervals:
                try:
                    stream = BinanceKlineStream(symbol, itv, self.redis)
                    task = asyncio.create_task(stream.connect())
                    self.tasks.append(task)
                    connected += 1
                except Exception as e:
                    print(f"⚠️ 启动 {symbol}-{itv} 失败: {e}")

        elapsed = time.time() - start_time
        print(f"✅ Binance Stream 启动完成，共监听 {connected}/{total} 条流，用时 {elapsed:.2f}s")

        # 启动心跳
        asyncio.create_task(self._heartbeat())

    async def _heartbeat(self):
        """输出当前活跃流状态"""
        while True:
            active = len(STREAM_HEARTBEAT)
            print(f"💗 Binance Stream Heartbeat: {active} active streams")
            await asyncio.sleep(60)

    async def stop(self):
        """安全关闭"""
        for task in self.tasks:
            task.cancel()
        self.tasks.clear()
        print("🧹 Binance 行情流全部停止")


# =========================================================
# 启动入口
# =========================================================
kline_hub = None


async def start_realtime_market(pairs: List[List[str]] = None):
    """FastAPI 启动时运行（热门币自动采集）"""
    global kline_hub
    if not pairs:
        # 从数据库加载前20个热门币
        result = await CryptoAsset.get(one=False, is_hot=True)
        pairs = [[f"{a.symbol.upper()}USDT", ["1m"]] for a in result[:20]]

    kline_hub = KlineHub(pairs)
    await kline_hub.start()
    print("✅ Binance 实时行情后台任务已启动")
