"""
# @Time    : 2025/10/28 6:37
# @Author  : Pedro
# @File    : test.py
# @Software: PyCharm
"""
import hashlib

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
sha256_pwd = hashlib.sha256("123123".encode("utf-8")).hexdigest()
hashed = pwd_context.hash(sha256_pwd)
print(hashed)
print(pwd_context.verify(sha256_pwd, hashed))
