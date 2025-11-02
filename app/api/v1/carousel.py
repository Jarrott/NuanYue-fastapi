"""
# @Time    : 2025/11/1 0:10
# @Author  : Pedro
# @File    : carousel.py
# @Software: PyCharm
"""
import time

from fastapi import APIRouter, Query

from app.api.v1.schema.response import CarouselListResponse
from app.api.v1.schema.response import PedroResponse
from app.api.v1.services.carousel import CarouselService

rp = APIRouter(prefix="/public", tags=["平台APP端公共资源"])

@rp.get("/get/banners", summary="获取轮播图")
async def get_carousel(country: str | None = Query(None, description="国家，例：CN/JP/US/KR")):
    items = await CarouselService.list_by_country(country)
    print({"items": items})
    return CarouselListResponse(msg=f"获取{country}的轮播图成功",items=items)

@rp.post("/ping",name="客户端延迟")
async def ping(payload: dict):
    client_send_time = payload.get("client_time")
    server_time = int(time.time() * 1000)
    return {
        "client_time": client_send_time,
        "server_time": server_time
    }