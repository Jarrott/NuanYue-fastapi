import importlib
import pkgutil
import time
from fastapi import APIRouter

def create_v1() -> APIRouter:
    """
    自动扫描 app.api.v1 下所有包含 rp 对象的模块，并注册到 router_v1
    """
    router_v1 = APIRouter(prefix="/v1", tags=["v1"])

    package_name = "app.api.v1"
    package = importlib.import_module(package_name)

    print("🚀 正在扫描并注册 v1 模块 ...\n")
    start_time = time.time()

    skip_modules = {"__init__", "model", "schema", "validator", "exception", "handler"}

    for _, module_name, is_pkg in pkgutil.iter_modules(package.__path__):
        if is_pkg or module_name in skip_modules:
            continue

        full_module = f"{package_name}.{module_name}"
        try:
            module = importlib.import_module(full_module)
            rp = getattr(module, "rp", None)
            if rp:
                router_v1.include_router(rp)
                route_count = len(rp.routes)
                print(f"✅ 已注册子模块: {module_name:<12} | prefix={rp.prefix or '/'} | tags={rp.tags} | routes={route_count}")
            else:
                print(f"⚠️ 模块 {module_name:<12} 未定义 rp 对象，已跳过。")
        except Exception as e:
            print(f"❌ 模块 {module_name:<12} 加载失败: {e}")

    elapsed = (time.time() - start_time) * 1000
    print(f"\n🌿 所有子模块注册完成！耗时 {elapsed:.2f} ms\n")

    return router_v1
