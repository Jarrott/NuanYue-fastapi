"""
# @Time    : 2025/10/28 11:44
# @Author  : Pedro
# @File    : spider.py
# @Software: PyCharm
"""
from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.v1.schema.response import HotCryptoResponse
from app.api.v1.model.crypto_assets import CryptoAsset
from app.api.v1.schema.spider import CryptoAssetSchema
from app.api.v1.validator.crypto_assets_service import CryptoCollectorService
from app.pedro.db import get_session
from app.pedro.exception import NotFound, Success
# from app.api.v1.schema.product import ShopProductListSchema
# from app.api.v1.schema.paging import PagingSchema
from app.api.v1.validator.shop_product_service import ProductCollectorService

# from app.api.v1.validator.crypto_assets_service import CryptoCollectorService

rp = APIRouter(prefix="/spider", tags=["商品模块"])


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


@rp.get("/crypto/hot", summary="热门虚拟货币列表",response_model=list[CryptoAssetSchema])
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


@rp.get("/crypto/trending", summary="趋势榜虚拟货币列表",response_model=HotCryptoResponse)
async def get_trending_assets(limit: int = Query(20, description="返回数量")):
    async with get_session() as session:
        result = await session.execute(
            select(CryptoAsset)
            .where(CryptoAsset.is_trending == True)
            .order_by(CryptoAsset.market_cap_rank.asc())
            .limit(limit)
        )
        return result.scalars().all()
