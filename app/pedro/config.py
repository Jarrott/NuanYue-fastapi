# -*- coding: utf-8 -*-
"""
@Time    : 2025/10/28
@Author  : Pedro
@File    : config.py
@Software: PyCharm

Pedro-Core Enterprise Config System (Safe Edition)
---------------------------------------------------
✅ 自动加载根目录 .env
✅ YAML 支持 ${ENV_VAR} 占位符解析
✅ 自动根据 APP_ENV 加载 development.yaml / production.yaml
✅ 深度递归合并配置（不会丢失默认值）
✅ 支持动态注册未知模块（cloud/email/kafka/...）
✅ 线程安全单例 + FastAPI 注册
✅ 保持与原参数命名完全一致
"""

import os
import re
import json
import yaml
import threading
from functools import lru_cache
from typing import Optional, Any, Dict
from fastapi import FastAPI
from dotenv import load_dotenv
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


# ======================================================
# 🔧 加载 .env 文件
# ======================================================
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
ENV_PATH = os.path.join(BASE_DIR, ".env")
if os.path.exists(ENV_PATH):
    load_dotenv(ENV_PATH, override=True)
    print(f"✅ 已加载环境文件: {ENV_PATH}")
else:
    print(f"⚠️ 未找到 .env 文件: {ENV_PATH}")


# ======================================================
# 🧩 内置基础配置模型
# ======================================================
class AppConfig(BaseModel):
    name: str = "Pedro-Core"
    version: str = "0.1.0"
    env: str = "dev"
    debug: bool = True
    log_level: str = "DEBUG"
    timezone: str = "Asia/Tokyo"
    host: str = "127.0.0.1"
    port: int = 8080
    oss_domain: str = None


class DatabaseConfig(BaseModel):
    url: str = "sqlite+aiosqlite:///./app.db"


class ExtraConfig(BaseModel):
    default: Optional[dict] = None


class AuthConfig(BaseModel):
    secret: str = "Pedro-Core"
    access_expires_in: int = 3600
    refresh_expires_in: int = 1


class RedisConfig(BaseModel):
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    redis_url: str = None

    @property
    def url(self):
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"


class TencentTMTConfig(BaseModel):
    secret_id: Optional[str] = None
    secret_key: Optional[str] = None


class TencentConfig(BaseModel):
    tmt: TencentTMTConfig = TencentTMTConfig()

class FirebaseConfig(BaseModel):
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    api_key: Optional[str] = None
    project_id: Optional[str] = None
    auth_domain: Optional[str] = None
    database_url: Optional[str] = None
    storage_bucket: Optional[str] = None
    messaging_sender_id: Optional[str] = None
    app_id: Optional[str] = None
    measurement_id: Optional[str] = None
    service_account_path: Optional[str] = None


class GoogleConfig(BaseModel):
    firebase: FirebaseConfig = FirebaseConfig()


class RabbitMQConfig(BaseModel):
    host: str = "localhost"
    port: int = 5672
    username: str = "guest"
    password: str = "guest"
    virtual_host: str = "/"
    url: Optional[str] = None
    default_exchange: str = ""
    default_queue: str = "default"

    @property
    def amqp_url(self):
        return self.url or f"amqp://{self.username}:{self.password}@{self.host}:{self.port}/{self.virtual_host}"


# ======================================================
# 🧠 工具函数
# ======================================================
def deep_merge(base: dict, override: dict) -> dict:
    """递归合并字典"""
    result = base.copy()
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def substitute_env_vars(value: Any) -> Any:
    """解析 ${VAR} 变量"""
    if isinstance(value, str):
        matches = re.findall(r"\$\{([^}^{]+)\}", value)
        for var in matches:
            env_val = os.getenv(var)
            if env_val:
                value = value.replace(f"${{{var}}}", env_val)
    elif isinstance(value, dict):
        return {k: substitute_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [substitute_env_vars(v) for v in value]
    return value


def load_yaml_config(env: str) -> Dict[str, Any]:
    """加载 YAML 配置文件并解析环境变量"""
    config_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../config"))
    file_path = os.path.join(config_dir, f"{env}.yaml")
    if not os.path.exists(file_path):
        print(f"⚠️ 未找到配置文件: {file_path}，使用默认配置。")
        return {}

    with open(file_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    print(f"✅ 已加载配置文件: {file_path}")
    return substitute_env_vars(data)


# ======================================================
# 🌍 Settings 主配置类
# ======================================================
class Settings(BaseSettings):
    app: AppConfig = AppConfig()
    database: DatabaseConfig = DatabaseConfig()
    redis: RedisConfig = RedisConfig()
    rabbitmq: RabbitMQConfig = RabbitMQConfig()
    extra: ExtraConfig = ExtraConfig()
    auth: AuthConfig = AuthConfig()
    tencent: TencentConfig = TencentConfig()
    google: GoogleConfig = GoogleConfig()

    model_config = SettingsConfigDict(env_file_encoding="utf-8", extra="allow")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        env = os.getenv("APP_ENV", self.app.env or "dev")
        yaml_data = load_yaml_config(env)

        # ✅ 自动递归更新现有模块
        for field_name, field in self.__fields__.items():
            section = yaml_data.get(field_name)
            current_val = getattr(self, field_name)
            if section and isinstance(current_val, BaseModel):
                merged = deep_merge(current_val.model_dump(), section)
                setattr(self, field_name, type(current_val)(**merged))

        # ✅ 动态注册未知模块
        for section_name, section_data in yaml_data.items():
            if section_name not in self.__dict__:
                if isinstance(section_data, dict):
                    DynamicConfig = type(
                        f"{section_name.title()}Config",
                        (BaseModel,),
                        {"__annotations__": {k: type(v) for k, v in section_data.items()}},
                    )
                    setattr(self, section_name, DynamicConfig(**section_data))
                    print(f"🧩 自动注册配置模块: {section_name}")
                else:
                    setattr(self, section_name, section_data)

    def summary(self):
        """输出配置概要"""
        print(f"\n🌍 [{self.app.env}] {self.app.name} 配置概览：")
        for name, value in self.__dict__.items():
            if isinstance(value, BaseModel):
                print(f"🧩 {name}: {value.model_dump()}")
        print("========================================\n")


# ======================================================
# 🧷 单例实例
# ======================================================
_settings_instance: Optional[Settings] = None
_settings_lock = threading.Lock()


@lru_cache()
def get_settings() -> Settings:
    """加载配置（带缓存）"""
    s = Settings()
    s.summary()
    return s


def get_current_settings() -> Settings:
    """线程安全全局访问"""
    global _settings_instance
    if _settings_instance is None:
        with _settings_lock:
            if _settings_instance is None:
                _settings_instance = get_settings()
    return _settings_instance


def init_settings(app: Optional[FastAPI] = None) -> Settings:
    """注册 FastAPI"""
    settings = get_current_settings()
    if app:
        app.state.settings = settings
    return settings
