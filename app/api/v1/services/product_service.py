from sqlalchemy import select, func
from app.pedro.db import async_session_factory
from app.api.v1.model.shop_product import ShopProduct
from app.api.v1.schema.response import ProductResponse


class ProductService:

    @staticmethod
    async def list_products(keyword=None, category=None, brand=None, order_by="id", sort="desc", page=1, size=10):
        async with async_session_factory() as session:

            query = select(ShopProduct)

            if keyword:
                query = query.where(ShopProduct.title.ilike(f"%{keyword}%"))
            if category:
                query = query.where(ShopProduct.category == category)
            if brand:
                query = query.where(ShopProduct.brand == brand)

            # total count
            total = await session.scalar(
                select(func.count()).select_from(query.subquery())
            )

            # ordering
            col = getattr(ShopProduct, order_by)
            col = col.desc() if sort == "desc" else col.asc()
            query = query.order_by(col)

            query = query.offset((page - 1) * size).limit(size)

            rows = (await session.execute(query)).scalars().all()

            # ✅ ORM → Pydantic
            items = [ProductResponse.model_validate(obj) for obj in rows]

            return items, total
