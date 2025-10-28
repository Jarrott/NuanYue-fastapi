"""
# @Time    : 2025/10/29 0:15
# @Author  : Pedro
# @File    : constances.py
# @Software: PyCharm
"""
# app/extension/rabbitmq/constants.py
EXCHANGE_DELAY = "delayed_exchange"         # 用新名字，避免之前 durable 冲突
QUEUE_ORDER_DELAY = "order.delay"
ROUTING_ORDER_DELAY = QUEUE_ORDER_DELAY      # 直连路由键=队列名
