# @Time    : 2025/11/8 16:45
# @Author  : Pedro
# @File    : add_fake_users.py
# @Software: PyCharm

import asyncio
import uuid
from typing import List, Dict

from faker import Faker
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.pedro.db import async_session_factory
from app.api.v1.model.virtual_users import VirtualUser  # 按你的路径调整

# fake = Faker("ja_JP")
fake = Faker("en_US")


async def create_virtual_users(n: int = 2000, batch_size: int = 500):
    """
    批量生成虚拟用户：本地去重 + PG on_conflict_do_nothing 兜底
    直到真正插入数量达到 n
    """
    inserted_total = 0

    # 为了减少 Faker 碰撞风险，额外本地去重
    seen_usernames = set()
    seen_emails = set()

    async with async_session_factory() as session:
        while inserted_total < n:
            need = n - inserted_total
            # 适度放大生成量，提高每轮有效插入率（避免 DO NOTHING 过多）
            gen_size = min(batch_size, max(100, need))

            rows: List[Dict] = []
            for _ in range(gen_size * 2):  # 放大2倍，过滤后更容易插满一批
                # 1) 用 faker.unique 降低碰撞
                username = fake.unique.user_name()
                email = fake.unique.email()

                # 2) 再用本地 set 双重去重
                if username in seen_usernames or email in seen_emails:
                    continue

                seen_usernames.add(username)
                seen_emails.add(email)

                rows.append({
                    "id": uuid.uuid4(),
                    "locale": fake.locale(),
                    "username": username,
                    "postcode": fake.postcode(),
                    "email": email,
                    "region": fake.city(),
                    "address": fake.address(),
                    "is_bot": True,
                    # 你的表里如果还有 create_time / update_time / device_info 等字段，
                    # 可以在此补充默认值
                })

                if len(rows) >= gen_size:
                    break

            if not rows:
                # 极端情况下 faker.unique 池子耗尽，清空重置
                fake.unique.clear()
                continue

            # ✅ 关键：PG upsert（不指定冲突目标 => 任意唯一约束冲突都 DO NOTHING）
            stmt = pg_insert(VirtualUser.__table__).values(rows).on_conflict_do_nothing()

            result = await session.execute(stmt)
            await session.commit()

            # rowcount 即本轮真正插入成功的行数（被 DO NOTHING 的不会计数）
            inserted = result.rowcount or 0
            inserted_total += inserted

            print(f"本轮生成 {len(rows)}，成功插入 {inserted}，累计 {inserted_total}/{n}")

    # 释放 faker 唯一池
    fake.unique.clear()
    print(f"✅ 完成：共插入 {inserted_total} 条虚拟用户")


if __name__ == "__main__":
    asyncio.run(create_virtual_users(n=10000, batch_size=1000))
