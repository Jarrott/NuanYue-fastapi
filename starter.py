# -*- coding: utf-8 -*-
"""
Pedro-Core FastAPI 启动文件
--------------------------------
入口职责：
✅ 调用 create_app()
✅ 启动 uvicorn
"""

import logging
import uvicorn
from app import create_app
from app.config.settings_manager import get_current_settings

settings = get_current_settings()
app = create_app()

if __name__ == "__main__":
    logging.getLogger("uvicorn.error").setLevel(logging.ERROR)
    print("🚀 Pedro-Core FastAPI 正在启动 ...")

    uvicorn.run(
        "starter:app",
        host=settings.app.host,
        port=settings.app.port,
        reload=settings.app.debug,
    )
