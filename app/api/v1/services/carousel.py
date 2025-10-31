"""
# @Time    : 2025/11/1 0:02
# @Author  : Pedro
# @File    : carousel.py
# @Software: PyCharm
"""
# app/services/carousel_service.py
from app.pedro import async_session_factory
from app.api.v1.model.carousel import Carousel
from app.pedro.service_manager import ServiceManager

CACHE_TTL = 120  # 2分钟缓存


class CarouselService:
    @staticmethod
    async def list_by_country(country: str):
        rds = ServiceManager.get("redis")
        key = f"carousel:{country}"

        cache = await rds.get(key)
        if cache:
            return cache

        rows = await Carousel.get(country=country, one=False)

        data = [
            {"id": c.id, "image": c.image, "link": c.link}
            for c in rows
        ]

        await rds.set(key, data, ex=CACHE_TTL)
        return data

    @staticmethod
    async def clear_cache(country: str):
        await ServiceManager.get("redis").delete(f"carousel:{country}")
