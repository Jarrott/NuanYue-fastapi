"""
# @Time    : 2025/10/26 4:28
# @Author  : Pedro
# @File    : plugin.py
# @Software: PyCharm
"""
# -*- coding: utf-8 -*-
from typing import List
from fastapi import FastAPI
from .redprint import Redprint

class PluginManager:
    def __init__(self):
        self._routers: List[Redprint] = []

    def mount(self, rp: Redprint):
        self._routers.append(rp)

    def register_to(self, app: FastAPI):
        for rp in self._routers:
            app.include_router(rp.router)

plugin_manager = PluginManager()