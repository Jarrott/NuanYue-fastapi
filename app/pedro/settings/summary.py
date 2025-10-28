"""
# @Time    : 2025/10/28 1:40
# @Author  : Pedro
# @File    : summary.py
# @Software: PyCharm
"""
from . import get_settings

def print_summary():
    s = get_settings()
    print(f"\n🌍 当前环境: {s.app.env}")
    for k, v in s.dict().items():
        print(f"🧩 {k}: {type(v).__name__}")
    print()
