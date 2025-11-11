"""
# @Time    : 2025/11/02 18:30
# @Author  : Pedro
# @File    : product.py
# @Software: PyCharm
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, asc, or_, select

from app.api.v1.model.shop_product import ShopProduct
from app.api.v1.schema.merchant import ProductSchema
from app.api.v1.schema.response import PedroResponse
from app.api.v1.schema.response import ProductResponse, ProductDetailResponse
from app.api.v1.services.product_service import ShopProduct, ProductService
from app.api.v1.schema.user import PageQuery, SearchShopSchema, SearchHistoryShopSchema  # 上面定义的分页入参
from app.pedro.pedro_jwt import login_required, optional_login
from app.pedro.response_adapter import PedroResponseAdapter

rp = APIRouter(prefix="/products", tags=["Products"])


@rp.get("/", name="商品列表", response_model=PedroResponse[list[ProductSchema]])
async def product_list(
        page_query: PageQuery = Depends(),
        keyword: str | None = None,
        category: str | None = None,
        brand: str | None = None,
        featured: Optional[bool] = Query(None, description="是否精选"),
        order_by: str = "id",
        sort: str = "desc",
        user=Depends(optional_login),  # ✅ 改为可选登录
):
    """
    商品列表接口（支持游客访问 + 登录后显示收藏状态）
    """
    uid = user.id if user else None  # ✅ 无登录时为 None

    items, total = await ProductService.list_products(
        uid=uid,  # ✅ 传入 uid（可能为 None）
        keyword=keyword,
        category=category,
        brand=brand,
        featured=featured,
        order_by=order_by,
        sort=sort,
        page=page_query.page,
        size=page_query.size,
    )

    # ✅ 返回分页响应
    return PedroResponse.page(
        items=items,
        total=total,
        page=page_query.page,
        size=page_query.size,
        msg="商品列表获取成功",
        schema=ProductSchema,
    )


@rp.get("/{product_id}", name="商品详情", response_model=PedroResponse[list[ProductDetailResponse]])
async def product_detail(product_id: int, current_user=Depends(login_required)):
    product = await ProductService.get_detail(current_user.id, product_id)
    return PedroResponse.success(data=product, schema=ProductDetailResponse)


@rp.get("/es/search", name="用户搜索商品")
async def product_find(keyword: str = Query(), user=Depends(login_required)):
    product = await ProductService.search_products(user.id, keyword)
    return product


@rp.get("/search/history", name="用户搜索记录", response_model=PedroResponse[list[SearchHistoryShopSchema]])
async def search_history(user=Depends(login_required)):
    history = await ProductService.list_search_history(user.id)
    return PedroResponse.success(data=history, schema=SearchHistoryShopSchema)


@rp.delete("/search/history", summary="清空用户搜索记录")
async def clear_history(user=Depends(login_required)):
    return await ProductService.clear_search_history(user.id)
