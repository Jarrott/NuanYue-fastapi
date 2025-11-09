"""
# @Time    : 2025/10/28 11:44
# @Author  : Pedro
# @File    : spider.py
# @Software: PyCharm
"""
import asyncio
import os
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.v1.model.virtual_users import VirtualUser
from app.api.v1.schema.response import HotCryptoResponse
from app.api.v1.model.crypto_assets import CryptoAsset
from app.api.v1.schema.spider import CryptoAssetSchema
from app.api.v1.services.crypto_assets_service import CryptoCollectorService
from app.pedro.config import get_current_settings
from app.pedro.db import get_session
from app.pedro.exception import NotFound, Success
# from app.api.v1.schema.product import ShopProductListSchema
# from app.api.v1.schema.paging import PagingSchema
from app.api.v1.services.shop_product_service import ProductCollectorService
from app.pedro.response import PedroResponse

# from app.api.v1.validator.crypto_assets_service import CryptoCollectorService

rp = APIRouter(prefix="/spider", tags=["商品模块"], include_in_schema=False)


# ======================================================
# 🛍️ 采集电商商品
# ======================================================
@rp.get("/shop", summary="采集电商商品信息")
async def collect_shop_products(limit: int = Query(100, description="采集数量"),
                                lang: str = Query("en", description="语言标识")):
    """
    异步采集电商商品数据并存储到数据库中
    """
    products = await ProductCollectorService.fetch_and_store(limit, lang)
    if not products:
        raise NotFound("没有采集成功")
    raise Success("电商商品信息采集成功")


#
# # ======================================================
# # 🛒 商品列表查询（支持分页、搜索）
# # ======================================================
# @router.get("/shops", response_model=ShopProductListSchema, summary="商品列表查询")
# async def get_shop_products(
#     db: AsyncSession = Depends(get_session),
#     page: int = Query(1, ge=1, description="页码"),
#     count: int = Query(10, ge=1, le=100, description="每页数量"),
# ):
#     """
#     商品列表查询（支持分页 / 搜索 / 排序）
#     """
#     offset = (page - 1) * count
#
#     total_query = await db.execute(select(ShopProduct))
#     total = len(total_query.scalars().all())
#
#     query = await db.execute(
#         select(ShopProduct)
#         .order_by(text("updated_at desc"))
#         .offset(offset)
#         .limit(count)
#     )
#
#     items = query.scalars().all()
#     total_page = math.ceil(total / count)
#
#     return ShopProductListSchema(
#         page=page,
#         count=count,
#         total=total,
#         total_page=total_page,
#         items=items
#     )


# ======================================================
# 💰 采集虚拟货币信息
# ======================================================
@rp.get(
    path="/crypto",
    summary="采集虚拟货币商品信息",
)
async def collect_crypto_assets(limit: int = Query(default=100, description="采集数量")):
    """
    异步采集虚拟货币列表（调用外部 API）
    """
    result = await CryptoCollectorService.fetch_and_store(limit=limit)

    if not result or result.get("status") != "success":
        raise NotFound("没有采集成功")
    raise Success("虚拟货币信息采集成功")


@rp.get("/crypto/hot", summary="热门虚拟货币列表", response_model=list[CryptoAssetSchema])
async def get_hot_assets(limit: int = Query(20, description="返回数量")):
    async with get_session() as session:
        result = await session.execute(
            select(CryptoAsset)
            .where(CryptoAsset.is_hot == True)
            .order_by(CryptoAsset.market_cap_rank.asc())
            .limit(limit)
        )
        assets = result.scalars().all()
        return assets


@rp.get("/crypto/trending", summary="趋势榜虚拟货币列表", response_model=HotCryptoResponse)
async def get_trending_assets(limit: int = Query(20, description="返回数量")):
    async with get_session() as session:
        result = await session.execute(
            select(CryptoAsset)
            .where(CryptoAsset.is_trending == True)
            .order_by(CryptoAsset.market_cap_rank.asc())
            .limit(limit)
        )
        return result.scalars().all()


# banners采集
settings = get_current_settings()
UNSPLASH_ACCESS_KEY = settings.unsplash.access_key
SAVE_DIR = Path(settings.storage.banners_path)

keywords = {
    "jp": ["japan banner", "tokyo marketing", "japan travel"],
    "cn": ["china banner", "shanghai skyline", "beijing city"],
    "us": ["usa business banner", "new york skyline"],
    "kr": ["korea seoul banner", "seoul skyline"],
}


async def fetch_images(query: str, per_page: int = 5):
    url = "https://api.unsplash.com/search/photos"
    params = {
        "query": query,
        "client_id": UNSPLASH_ACCESS_KEY,
        "per_page": per_page,
        "orientation": "landscape"
    }

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()
        return [img["urls"]["full"] for img in data.get("results", [])]


async def download_image(url: str, country: str, filename: str):
    country_dir = SAVE_DIR / country
    country_dir.mkdir(parents=True, exist_ok=True)

    parsed = urlparse(url)
    ext = os.path.splitext(parsed.path)[-1] or ".jpg"
    save_path = country_dir / f"{filename}{ext}"

    async with httpx.AsyncClient(timeout=40) as client:
        try:
            r = await client.get(url)
            r.raise_for_status()
            save_path.write_bytes(r.content)
            print(f"✅ Saved: {save_path}")
            return str(save_path)
        except Exception as e:
            print(f"❌ Failed {url}: {e}")
            return None


async def crawl_banners(limit: int = 3):
    result = {}

    tasks = []
    for country, kws in keywords.items():
        result[country] = []
        for kw in kws:
            urls = await fetch_images(kw, per_page=limit)

            for i, url in enumerate(urls):
                filename = f"{kw.replace(' ', '_')}_{i}"
                tasks.append(
                    download_image(url, country, filename)
                )

    finished = await asyncio.gather(*tasks)
    return {"status": "success", "saved": [f for f in finished if f]}


@rp.get("/banners")
async def api_download_banners(limit: int = Query(3, ge=1, le=10)):
    """
    下载不同国家 Banner 图到本地目录
    """
    res = await crawl_banners(limit)
    return res


@rp.get("/virtual/users")
async def get_virtual_users():
    add = await VirtualUser.email
    if add:
        return PedroResponse.success(data=add)
    return False
