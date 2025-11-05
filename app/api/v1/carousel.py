"""
# @Time    : 2025/11/1 0:10
# @Author  : Pedro
# @File    : carousel.py
# @Software: PyCharm
"""
import time

from fastapi import APIRouter, Query, Header

from app.api.v1.model.carousel import Carousel
from app.api.v1.model.category import Category
from app.api.v1.schema.response import CarouselListResponse, CategoryListResponse, BannerListResponse
from app.api.v1.schema.response import PedroResponse
from app.api.v1.services.carousel import CarouselService
from app.pedro.utils import normalize_lang

rp = APIRouter(prefix="/public", tags=["平台APP端公共资源"])


@rp.get("/get/banners", name="获取轮播图",response_model=BannerListResponse)
async def get_carousel(lang: str = Header(default=None, alias="Snap-App-Language")):
    lang = normalize_lang(lang)

    items = await Carousel.get(country=lang, one=False)
    if not items:
        return PedroResponse.fail(msg="数据有误")
    return BannerListResponse(data=items)


@rp.get("/categories", name="获取商品分类", response_model=CategoryListResponse)
async def get_category(lang: str = Header(default=None, alias="Snap-App-Language")):
    lang = normalize_lang(lang)
    data = await Category.get(language=lang, one=False)

    print(lang,data)

    if not data:
        raise PedroResponse.fail(msg="数据错误")

    return CategoryListResponse(data=data)


@rp.post("/ping", name="客户端延迟")
async def ping(payload: dict):
    client_send_time = payload.get("client_time")
    server_time = int(time.time() * 1000)
    return {
        "client_time": client_send_time,
        "server_time": server_time
    }
