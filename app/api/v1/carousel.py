"""
# @Time    : 2025/11/1 0:10
# @Author  : Pedro
# @File    : carousel.py
# @Software: PyCharm
"""
from fastapi import APIRouter

from app.api.v1.model.carousel import Carousel
from app.api.v1.services.carousel import CarouselService

rp = APIRouter(prefix="/carousel", tags=["平台APP端公共资源"])

@rp.get("/get/banners")
def get_banners():

    banners = CarouselService.list_by_country("JP")

    return banners
