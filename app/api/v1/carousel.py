"""
# @Time    : 2025/11/1 0:10
# @Author  : Pedro
# @File    : carousel.py
# @Software: PyCharm
"""
import time

from fastapi import APIRouter, Query, Header, Depends

from app.api.v1.model.carousel import Carousel
from app.api.v1.model.category import Category
from app.api.v1.schema.public import FlashSaleTimeSchema
from app.api.v1.schema.response import CarouselListResponse, CategoryListResponse, BannerListResponse, BannerResponse, \
    CategoryResponse
from app.api.v1.schema.response import PedroResponse
from app.api.v1.schema.user import StoreSchema
from app.api.v1.services.carousel import CarouselService
from app.api.v1.services.fs.store_service import StoreServiceFS
from app.extension.google_tools.firebase_admin_service import rtdb
from app.extension.ycloud.send_email import send_signup_email
from app.pedro.utils import normalize_lang
from app.util.get_lang import get_lang

rp = APIRouter(prefix="/public", tags=["平台APP端公共资源"])


@rp.get("/banners", response_model=PedroResponse[list[BannerResponse]])
async def get_banners(lang: str = Depends(get_lang)):
    banners = await Carousel.get(country=lang, one=False)
    if not banners:
        return PedroResponse.fail(msg="无数据")
    return PedroResponse.success(data=banners, schema=BannerResponse)

@rp.get("/flash-sale/time",response_model=PedroResponse[FlashSaleTimeSchema])
async def get_flash_sale():
    flash_time = rtdb.reference("flash_sale/current").get()
    return PedroResponse.success(flash_time,schema=FlashSaleTimeSchema)

@rp.get("/categories", name="获取商品分类", response_model=PedroResponse[list[CategoryResponse]])
async def get_category(lang: str = Depends(get_lang)):
    data = await Category.get(language=lang, one=False)

    if not data:
        return PedroResponse.fail(msg="没有数据")

    return PedroResponse.success(data=data, schema=CategoryResponse)


@rp.get("/store/list", name="商家列表",response_model=PedroResponse[list[StoreSchema]])
async def get_stores(limit: int = Query(20, description="分页数量"),
                     keyword: str = Query(),
                     start_after: str = None):
    stores = await StoreServiceFS.list_stores(limit,keyword)
    return PedroResponse.success(msg="查询成功",data=stores,schema=StoreSchema)


@rp.post("/ping", name="客户端延迟")
async def ping(payload: dict):
    client_send_time = payload.get("client_time")
    server_time = int(time.time() * 1000)
    return {
        "client_time": client_send_time,
        "server_time": server_time
    }

@rp.post("/send/email",name="发送邮件")
async def send_email():
    await send_signup_email("JARROTT", "xqiqio7@gmail.com", "sasas")
    return PedroResponse.success()
