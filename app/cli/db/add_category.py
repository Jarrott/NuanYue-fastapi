"""
# @Time    : 2025/11/05 10:30
# @Author  : Pedro
# @File    : init_category.py
# @Software: PyCharm
"""


import asyncio
from app.api.v1.model.category import Category
from app.pedro import async_session_factory

# 分类初始化数据
CATEGORIES = [
    # name, slug, language, icon
    ("Women", "women", "en", "http://up.qi-yue.vip/category/women.png"),
    ("Men", "men", "en", "http://up.qi-yue.vip/category/man.png"),
    ("Sneakers", "sneaker", "en", "http://up.qi-yue.vip/category/sneaker.png"),
    ("Bags", "bag", "en", "http://up.qi-yue.vip/category/bag.png"),

    ("女性", "women-cn", "zh", "http://up.qi-yue.vip/category/women.png"),
    ("男性", "men-cn", "zh", "http://up.qi-yue.vip/category/man.png"),
    ("鞋子", "sneaker-cn", "zh", "http://up.qi-yue.vip/category/sneaker.png"),
    ("包包", "bag-cn", "zh", "http://up.qi-yue.vip/category/bag.png"),

    ("女性", "women-jp", "jp", "http://up.qi-yue.vip/category/women.png"),
    ("男性", "men-jp", "jp", "http://up.qi-yue.vip/category/man.png"),
    ("スニーカー", "sneaker-jp", "jp", "http://up.qi-yue.vip/category/sneaker.png"),
    ("バッグ", "bag-jp", "jp", "http://up.qi-yue.vip/category/bag.png"),
]


async def init_category():
    async with async_session_factory() as session:
        items = []

        for idx, (name, slug, lang, icon) in enumerate(CATEGORIES, start=1):
            items.append(
                Category(
                    name=name,
                    slug=slug,
                    language=lang,
                    icon=icon,
                    sort=idx,
                    is_active=True,
                )
            )

        session.add_all(items)
        await session.commit()
        print(f"✅ Category 初始化完成，共写入 {len(items)} 条分类数据")


if __name__ == "__main__":
    asyncio.run(init_category())
