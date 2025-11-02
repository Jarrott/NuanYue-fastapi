"""
# @Time    : 2025/11/1 23:22
# @Author  : Pedro
# @File    : add_lunbotu.py
# @Software: PyCharm
"""
# @Time    : 2025/11/1 00:01
# @Author  : Pedro
# @File    : populate_carousel.py
# @Software: PyCharm

import asyncio
from app.api.v1.model.carousel import Carousel
from app.pedro import async_session_factory


COUNTRIES = ["kr", "cn", "us", "jp"]
IMAGES_PER_COUNTRY = 5


async def init_carousel():
    async with async_session_factory() as session:
        items = []

        for country in COUNTRIES:
            for i in range(1, IMAGES_PER_COUNTRY + 1):
                url = f"http://up.qi-yue.vip/{country}/{i:02d}.jpg"
                items.append(
                    Carousel(
                        country=country.upper(),
                        image=url,
                        link=url,                     # 或者你的落地页
                        sort=i,
                        status=1
                    )
                )

        session.add_all(items)
        await session.commit()
        print(f"✅ 初始化完成，共写入 {len(items)} 条轮播图数据")


if __name__ == "__main__":
    asyncio.run(init_carousel())
