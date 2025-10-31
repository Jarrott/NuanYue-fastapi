from app.pedro.model import User
from app.extension.redis.redis_client import rds


# 要在__init__引入
async def handle_vip_expire(data: dict):
    user_id = data.get("user_id")
    if not user_id:
        return print("⚠️ vip_expire: 缺少 user_id")

    # 查库
    user = await User.get(id=user_id)
    if not user:
        return print(f"❌ VIP过期: 找不到用户 {user_id}")

    # 更新
    user.extra["vip"] = False
    await user.update(commit=True)

    print(f"👑 用户 {user_id} 的 VIP 已过期")
