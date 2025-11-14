"""
# @Time    : 2025/11/15 6:03
# @Author  : Pedro
# @File    : order_number_generator.py
# @Software: PyCharm
"""
import uuid
from datetime import datetime
import random
import hashlib


class OrderNumberGenerator:

    @staticmethod
    def generate(uid: str | int, prefix: str = "O") -> str:
        # 时间戳
        ts = datetime.now().strftime("%Y%m%d%H%M%S")

        # hash 用户 ID，取后 4 位
        uid_hash = hashlib.md5(str(uid).encode()).hexdigest()[:4].upper()

        # 随机 6 位数字
        rand = str(random.randint(100000, 999999))

        # return f"{prefix}-{ts}-{uid_hash}-{rand}"
        return f"{ts}{uid_hash}{rand}"
