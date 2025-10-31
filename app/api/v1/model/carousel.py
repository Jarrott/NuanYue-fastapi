"""
# @Time    : 2025/11/1 0:01
# @Author  : Pedro
# @File    : carousel.py
# @Software: PyCharm
"""
from sqlalchemy import Column, Integer, String, Text

from app.pedro.interface import InfoCrud


class Carousel(InfoCrud):
    __tablename__ = "carousel"

    id = Column(Integer, primary_key=True)
    country = Column(String(8), nullable=False)  # JP CN US SG ...
    image = Column(Text, nullable=False)         # CDN URL
    link = Column(Text, nullable=True)
    sort = Column(Integer, default=0)            # 排序
    status = Column(Integer, default=1)          # 1=active, 0=disabled
