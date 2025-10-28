from fastapi import APIRouter

from app.config.settings_manager import get_current_settings
from app.extension.rabbitmq.rabbit import rabbit
from app.pedro.exception import Success, NotFound
from app.extension.redis.redis_client import rds

rp = APIRouter(prefix="/book", tags=["图书"])


@rp.get("/api")
async def login():
    settings = get_current_settings()
    print(settings.extra.default)
    await rds.set("user:1001", {"name": "Pedro", "vip": True}, ex=3600)
    await rabbit.publish("ok", routing_key="task_queue")
    return Success("✅ book api loaded successfully")
