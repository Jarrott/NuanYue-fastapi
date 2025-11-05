"""
# @Time    : 2025/11/5 9:50
# @Author  : Pedro
# @File    : category.py
# @Software: PyCharm
"""
from sqlalchemy import Column, Integer, String, Boolean

from app.pedro.interface import InfoCrud


class Category(InfoCrud):
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False, comment="分类名称")
    slug = Column(String(120), unique=True, index=True, nullable=False, comment="URL Key / 唯一标识")
    language = Column(String(30), default="en")
    icon = Column(String(255), nullable=True, comment="分类图标")
    is_active = Column(Boolean, default=True, comment="是否启用")
    sort = Column(Integer, default=0, comment="排序字段")
