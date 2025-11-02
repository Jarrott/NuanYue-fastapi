"""
# @Time    : 2025/11/02 18:30
# @Author  : Pedro
# @File    : product.py
# @Software: PyCharm
"""
from fastapi import APIRouter, Depends
from app.api.v1.schema.response import PedroResponse, PaginatedResponse
from app.api.v1.schema.response import ProductResponse, ProductDetailResponse
from app.api.v1.services.product_service import ProductService
from app.api.v1.schema.user import PageQuery  # 上面定义的分页入参

rp = APIRouter(prefix="/products", tags=["Products"])


@rp.get("/",name="商品列表")
async def product_list(
    page_query: PageQuery = Depends(),
    keyword: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    order_by: str = "id",
    sort: str = "desc"
):
    items, total = await ProductService.list_products(
        keyword=keyword,
        category=category,
        brand=brand,
        order_by=order_by,
        sort=sort,
        page=page_query.page,
        size=page_query.size
    )

    return PedroResponse.page(items=items, total=total, page=1, size=10)


@rp.get("/{product_id}")
async def product_detail(product_id: int):
    from sqlalchemy import select
    from app.pedro.db import async_session_factory
    from app.api.v1.model.shop_product import ShopProduct

    async with async_session_factory() as session:
        row = await session.scalar(select(ShopProduct).where(ShopProduct.id == product_id))
        if not row:
            return PedroResponse.fail("Product not found")

        return PedroResponse.success(ProductDetailResponse.model_validate(row))
