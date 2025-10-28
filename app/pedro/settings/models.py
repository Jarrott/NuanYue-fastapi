"""
# @Time    : 2025/10/28 1:39
# @Author  : Pedro
# @File    : models.py
# @Software: PyCharm
"""
from pydantic import BaseModel
from typing import Optional, Dict, Any

class AppConfig(BaseModel):
    name: str = "Pedro-Core"
    env: str = "dev"
    debug: bool = True
    port: int = 8000

class DatabaseConfig(BaseModel):
    url: str = "sqlite+aiosqlite:///./app.db"
    pool_size: int = 10
    echo: bool = False
    auto_create: bool = True


class SettingsModel(BaseModel):
    app: AppConfig = AppConfig()
    database: DatabaseConfig = DatabaseConfig()
    default: Optional[Dict[str, Any]] = None
