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
from app.api.v1.schema.user import PageQuery  # 上面定义的分页入参
from app.pedro.pedro_jwt import login_required
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
):
    test = await ShopProduct.get(featured=featured, one=False)

    print(test)
    items, total = await ProductService.list_products(
        keyword=keyword,
        category=category,
        brand=brand,
        featured=featured,
        order_by=order_by,
        sort=sort,
        page=page_query.page,
        size=page_query.size,
    )

    return PedroResponse.page(
        items=items, total=total,
        page=page_query.page, size=page_query.size,
        msg="商品列表获取成功",
        schema=ProductSchema
    )


@rp.get("/{product_id}", name="商品详情", response_model=ProductDetailResponse)
async def product_detail(product_id: int, current_user=Depends(login_required)):
    row = await ShopProduct.get(id=product_id)

    if not row:
        return PedroResponse.fail("Product not found")

    # ✅ 转 Pydantic Schema
    product = ProductDetailResponse.model_validate(row)

    # ✅ 直接 success 包装（data 仅在有值时出现）
    return PedroResponse.success(product)
