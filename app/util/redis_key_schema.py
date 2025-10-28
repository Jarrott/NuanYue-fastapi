"""
# @Time    : 2025/10/28 3:33
# @Author  : Pedro
# @File    : redis_key_schema.py
# @Software: PyCharm
"""
"""
# @Time    : 2025/10/8 12:23
# @Author  : Pedro
# @File    : redis_key_schema.py
# @Software: PyCharm
"""

# 规范使用redis key 避免手写每个key出错
def redis_key_user_socket(uid: int) -> str:

    """用户 Socket.IO 连接的 Redis Key"""
    return f"socketio:user:{uid}"

def redis_key_user_referral(uid: int) -> str:
    """用户邀请关系"""
    return f"user:referral:{uid}"

def redis_key_vip_status(uid: int) -> str:
    """用户 VIP 状态"""
    return f"user:vip:{uid}"

def redis_key_user_token_version(uid: int) -> str:
    """用户Token版本"""
    return f"user:token_version:{uid}"

def redis_key_user_cache_token(uid: int) -> str:
    """用户缓存信息"""
    return f"user:cache_token:{uid}"

def redis_key_user_referral_tree(uid: int) -> str:
    """用户代理层级缓存"""
    return f"user:referral_tree:{uid}"

def daily_recharge(uid: int) -> str:
    return f"daily:recharge:{uid}"
