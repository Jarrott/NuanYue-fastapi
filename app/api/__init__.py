"""
API 注册入口
"""
from app.api.v1 import create_v1

def register_blueprint(app):
    v1_router = create_v1()  # ✅ 调用函数
    app.include_router(v1_router)  # ✅ 不再加 prefix="/v1"
    print("✅ v1 路由注册成功")