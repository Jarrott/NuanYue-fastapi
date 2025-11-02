import asyncio
import json
import time
from typing import Callable, Awaitable, Optional
from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect
from app.extension.redis.redis_client import rds
from app.extension.websocket.wss import websocket_manager
from app.extension.websocket.utils.ws_utils import ws_auth
from app.pedro.pedro_jwt import jwt_service

# 默认策略
HEARTBEAT_INTERVAL = 20          # 客户端心跳频率（建议 15~30s）
IDLE_TIMEOUT = 60                # 超时踢下线（无心跳/无任何收发）
TOKEN_REFRESH_THRESHOLD = 5 * 60 # token 距离过期 < 5m，提示续期

async def _set_online(uid: int, ws_id: str):
    r = await rds.instance()
    # 在线集合 + 详情信息（可扩展 ip/ua）
    await r.sadd("ws:online:uids", uid)
    await r.hset(f"ws:online:detail:{uid}", mapping={
        "ws_id": ws_id,
        "last_seen": int(time.time())
    })

async def _set_offline(uid: int):
    r = await rds.instance()
    await r.srem("ws:online:uids", uid)
    await r.delete(f"ws:online:detail:{uid}")

async def _online_count() -> int:
    r = await rds.instance()
    return await r.scard("ws:online:uids")

def _now() -> int:
    return int(time.time())

async def ws_entry(
    ws: WebSocket,
    handler: Callable[[WebSocket, int], Awaitable[None]],
    *,
    auto_subscribe_all: bool = False,
    heartbeat_interval: int = HEARTBEAT_INTERVAL,
    idle_timeout: int = IDLE_TIMEOUT,
    enable_token_refresh: bool = True,
):
    await ws.accept()

    # 鉴权
    auth = await ws_auth(ws)

    if not auth:
        return
    uid, payload, token = auth

    # 记录连接（你已有的 manager）
    await websocket_manager.connect(ws, uid)
    await _set_online(uid, ws_id=str(id(ws)))
    await websocket_manager.subscribe(ws, f"user:{uid}")
    print(f"🟢 WS connected: uid={uid}")

    # 自动订阅全部频道（可按需实现 get_all_channels）
    if auto_subscribe_all and hasattr(websocket_manager, "get_all_channels"):
        channels = websocket_manager.get_all_channels()
        for ch in channels:
            await websocket_manager.subscribe(ws, ch)
        await ws.send_json({"type": "system", "msg": "subscribed_all", "channels": channels})

    last_seen = _now()

    # 心跳 + 超时监视器（后台协程）
    async def watchdog():
        nonlocal last_seen
        try:
            while True:
                await asyncio.sleep(1)
                if _now() - last_seen > idle_timeout:
                    await ws.send_json({"type": "system", "error": "idle_timeout"})
                    await ws.close(code=4004, reason="Idle timeout")
                    return
        except Exception:
            # 监视器结束即可
            return

    watchdog_task = asyncio.create_task(watchdog())

    # Token 即将过期提醒（只提醒一次）
    refresh_notified = False

    try:
        # 主循环：同时处理心跳、token 续期请求、业务消息
        while True:
            raw = await ws.receive_text()
            last_seen = _now()

            # 尝试解析为 JSON；允许纯文本
            try:
                msg = json.loads(raw)
            except Exception:
                msg = {"type": "text", "data": raw}

            mtype = msg.get("type") or msg.get("action")

            # --- 心跳：client -> { "type": "ping", "t": 123456 } ---
            if mtype == "ping":
                await ws.send_json({"type": "pong", "t": msg.get("t", _now())})
                # 更新 Redis 最后在线时间
                await _set_online(uid, ws_id=str(id(ws)))
                continue

            # --- Token 刷新：client -> { "action": "refresh", "refresh_token": "..." } ---
            if mtype == "refresh":
                try:
                    new_tokens = await jwt_service.verify_refresh_token(msg["refresh_token"])
                    await ws.send_json({"type": "token", "event": "refreshed", **new_tokens})
                    # 刷新后可以重置 refresh_notified
                    refresh_notified = False
                except Exception as e:
                    await ws.send_json({"type": "token", "event": "refresh_failed", "error": str(e)})
                continue

            # --- 业务：交给 handler ---
            await handler(ws, uid) if callable(handler) else None
            # 注意：如果 handler 内部也在 await ws.receive_text()，就将上面的 parse/分支移到 handler 中处理即可。
            # 此处是“网关层先拦截控制消息（心跳/续期），剩下的交给业务”。

            # --- Token 续期提醒（可与 handler 并存） ---
            if enable_token_refresh:
                exp = payload.get("exp")          # JWT exp (epoch seconds)
                if exp and (exp - _now()) < TOKEN_REFRESH_THRESHOLD and not refresh_notified:
                    refresh_notified = True
                    await ws.send_json({"type": "token", "event": "refresh_required", "remain_sec": exp - _now()})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"❌ WS error uid={uid}: {e}")
    finally:
        watchdog_task.cancel()
        await websocket_manager.disconnect(ws)
        await _set_offline(uid)
        print(f"🔴 WS disconnected: uid={uid}")
