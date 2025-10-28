# app/api/v1/order.py
from fastapi import APIRouter
import uuid, time
from app.pedro.service_manager import ServiceManager

rp = APIRouter(prefix="/order", tags=["订单"])

@rp.post("/create")
async def create_order(uid: str, item_id: str):
    """
    创建订单：
    - 写 Hash: order:data:{order_id}
    - 写状态: order:status:{order_id} = pending
    - 写哨兵: order:pending:{order_id} EX=10 （过期触发Keyspace事件）
    """
    order_id = f"{uid}:{uuid.uuid4().hex[:8]}"
    redis = ServiceManager.get("redis")

    await redis.hset(f"order:data:{order_id}", {
        "uid": uid,
        "item_id": item_id,
        "created_at": str(int(time.time())),
    })
    await redis.set(f"order:status:{order_id}", "pending")
    await redis.set(f"order:pending:{order_id}", "1", ex=10)  # TTL 10秒

    return {"order_id": order_id, "status": "pending", "ttl_seconds": 10}


@rp.post("/complete")
async def complete_order(order_id: str):
    """
    标记订单完成（在TTL内调用则不会触发过期推送）
    """
    redis = ServiceManager.get("redis")
    await redis.set(f"order:status:{order_id}", "completed")

    # 可选：立刻给用户推送「已完成」
    data = await redis.hgetall(f"order:data:{order_id}")
    uid = data.get("uid", "unknown")
    from app.extension.websocket.wss import websocket_manager
    await websocket_manager.send_to_user(uid, {
        "type": "order_completed",
        "order_id": order_id,
        "msg": "订单已完成 ✅"
    })

    return {"order_id": order_id, "status": "completed"}
