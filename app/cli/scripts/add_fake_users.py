# -*- coding: utf-8 -*-
"""
# @Time    : 2025/11/15 21:40
# @Author  : Pedro
# @File    : generate_virtual_users.py
# @Software: PyCharm
"""

import random
import uuid
import time
import asyncio

from app.extension.google_tools.firestore import fs_service


# ——————————————————————————
# 字典：随机模拟数据
# ——————————————————————————
first_names = [
    "Yuki","Mika","Sakura","Aoi","Rina",
    "Akira","Ren","Kaito","Haruto","Hinata",
    "Sora","Kaede","Yuma","Nao","Rui"
]

cities = [
    ("Tokyo", "Shinjuku-ku"), ("Tokyo", "Toshima-ku"),
    ("Osaka", "Kita-ku"), ("Nagoya", "Naka-ku"),
    ("Fukuoka", "Hakata-ku"), ("Sapporo", "Chuo-ku")
]

devices = [
    "iPhone 14", "iPhone 15 Pro", "Google Pixel 7",
    "Samsung S23", "Sony Xperia 5"
]

categories = [
    "beauty", "fashion", "electronics",
    "gaming", "household", "skincare"
]

freqs = ["daily", "2-3 days", "weekly", "monthly", "lazy"]

tags_list = ["活跃用户", "高复购", "新用户", "沉默用户", "优惠敏感"]


# ——————————————————————————
# 工具函数：生成邮箱+电话（带掩码）
# ——————————————————————————
def mask_email(name: str):
    return f"{name.lower()}***@gmail.com"

def mask_phone():
    return f"080-***{random.randint(1,9)}-{random.randint(1000,9999)}"


# ——————————————————————————
# 单个用户生成逻辑
# ——————————————————————————
def generate_single_user():
    name = random.choice(first_names)
    city, area = random.choice(cities)

    return {
        "uid": "u_" + uuid.uuid4().hex[:8],
        "nickname": name + "***",
        "gender": random.choice(["male", "female"]),
        "age": random.randint(18, 45),
        "email": mask_email(name),
        "phone": mask_phone(),
        "country": "JP",
        "city": city,
        "address": f"{area} {random.randint(1,5)}-{random.randint(1,20)}-{random.randint(1,20)}",
        "device": random.choice(devices),
        "order_frequency": random.choice(freqs),
        "preferred_categories": random.sample(categories, k=random.randint(1, 3)),
        "tags": random.sample(tags_list, k=2),
        "create_time": int(time.time() * 1000)
    }


# ——————————————————————————
# 批量生成并写入 Firestore
# ——————————————————————————
async def generate_virtual_users(num: int = 500):
    tasks = []

    for _ in range(num):
        user = generate_single_user()
        path = f"virtual_users/{user['uid']}"
        # 异步写入 Firestore
        tasks.append(fs_service.set(path, user))

    await asyncio.gather(*tasks)

    print(f"🎉 已成功生成并写入 {num} 个虚拟用户")


# ——————————————————————————
# 主入口
# ——————————————————————————
if __name__ == "__main__":
    asyncio.run(generate_virtual_users(500))
