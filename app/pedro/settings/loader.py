"""
# @Time    : 2025/10/28 1:39
# @Author  : Pedro
# @File    : loader.py
# @Software: PyCharm
"""
import yaml, json, os
from pathlib import Path

def load_config_file(env_name: str) -> dict:
    config_dir = Path(__file__).resolve().parent.parent.parent / "config"
    for ext in ("yaml", "yml", "json"):
        path = config_dir / f"{env_name}.{ext}"
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) if ext in ("yaml", "yml") else json.load(f)
                return data or {}
    return {}
