"""
# @Time    : 2025/11/5 6:51
# @Author  : Pedro
# @File    : crypto.py
# @Software: PyCharm
"""
from app.pedro.config import get_current_settings

from Crypto.Cipher import AES
import base64

settings = get_current_settings()

class AESCipher:
    def __init__(self, key: str, iv: str):
        self.key = key.encode("utf-8")
        self.iv = iv.encode("utf-8")

    @staticmethod
    def _pkcs7_pad(data: bytes) -> bytes:
        pad_len = 16 - len(data) % 16
        return data + bytes([pad_len]) * pad_len

    @staticmethod
    def _pkcs7_unpad(data: bytes) -> bytes:
        pad_len = data[-1]
        return data[:-pad_len]

    # 加密
    def encrypt(self, text: str) -> str:
        data = text.encode("utf-8")
        cipher = AES.new(self.key, AES.MODE_CBC, self.iv)
        encrypted = cipher.encrypt(self._pkcs7_pad(data))
        b64 = base64.b64encode(encrypted).decode()
        return b64

    # 解密
    def decrypt(self, b64: str) -> str:
        encrypted = base64.b64decode(b64)
        cipher = AES.new(self.key, AES.MODE_CBC, self.iv)
        decrypted = cipher.decrypt(encrypted)
        unpadded = self._pkcs7_unpad(decrypted)
        return unpadded.decode("utf-8")


cipher = AESCipher(settings.aes.secret, settings.aes.iv)
