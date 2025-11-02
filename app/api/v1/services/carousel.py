import json

from app.api.v1.model.carousel import Carousel
from app.pedro.service_manager import ServiceManager

CACHE_TTL=1200

class CarouselService:
    @staticmethod
    async def list_by_country(country: str):
        rds = ServiceManager.get("redis")
        key = f"carousel:{country.upper()}"

        cache = await rds.get(key)
        if cache:
            # ✅ 若是 bytes → decode → json
            if isinstance(cache, bytes):
                return json.loads(cache.decode())

            # ✅ 若是 str → json
            if isinstance(cache, str):
                return json.loads(cache)

            # ✅ 若是 list → 直接返回 (兼容旧缓存)
            if isinstance(cache, list):
                return cache

        # 🛢️ DB
        rows = await Carousel.get(country=country.upper(), one=False)

        data = [{"id": c.id, "image": c.image, "link": c.link} for c in rows]

        # ✅ 强制写入 JSON string
        await rds.set(key, json.dumps(data), ex=CACHE_TTL)
        return data
