from urllib.parse import parse_qs
from fastapi import WebSocket
from app.pedro.pedro_jwt import jwt_service   # 你已有
from typing import Optional, Tuple

async def ws_auth(ws: WebSocket) -> Optional[Tuple[int, dict, str]]:
    """
    返回 (uid, payload, token)。失败会自动 close，返回 None
    """
    query = parse_qs(ws.url.query)
    token = query.get("token", [None])[0]

    print("WS token received:", token)  # ✅ debug
    if not token:
        await ws.close(code=4001, reason="Missing token")
        return None

    try:
        payload = await jwt_service.verify(token)
        uid = int(payload["uid"])
        return uid, payload, token
    except Exception as e:
        await ws.close(code=4002, reason=f"Token invalid: {e}")
        return None
