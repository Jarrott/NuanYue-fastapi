# -*- coding: utf-8 -*-
"""
# @Time    : 2025/11/10 22:31
# @Author  : Pedro
# @File    : product_service.py
# @Software: PyCharm
"""
from typing import Optional, Tuple, List
from app.api.v1.model.shop_product import ShopProduct


class ProductService:
    """
    🧩 Pedro-Core 商品服务层
    ---------------------------------------------
    ✅ 基于 BaseCrud.paginate() 的统一分页查询
    ✅ 支持关键字模糊搜索、多条件过滤、排序
    ✅ 结果可直接传入 PedroResponse.page()
    """

    @staticmethod
    async def list_products(
        *,
        keyword: Optional[str] = None,
        category: Optional[str] = None,
        brand: Optional[str] = None,
        featured: Optional[bool] = None,
        order_by: str = "id",
        sort: str = "desc",
        page: int = 1,
        size: int = 10,
    ) -> Tuple[List[ShopProduct], int]:
        """
        🔍 获取商品列表（支持搜索、筛选、分页）
        ---------------------------------------------
        :param keyword: 搜索关键词（匹配 title / description / brand）
        :param category: 商品分类
        :param brand: 品牌
        :param featured: 是否推荐商品
        :param order_by: 排序字段
        :param sort: 排序方向（asc / desc）
        :param page: 页码
        :param size: 每页数量
        :return: (items, total)
        """

        # 🔸 构建过滤条件
        filters = {
            "category": category,
            "brand": brand,
            "featured": featured,
        }

        # 🔸 关键字模糊搜索字段
        keyword_fields = ["title", "description", "brand"]

        # 🔸 调用通用分页方法
        items, total = await ShopProduct.paginate(
            page=page,
            size=size,
            filters=filters,
            keyword=keyword,
            keyword_fields=keyword_fields,
            order_by=order_by,
            sort=sort,
        )

        return items, total
