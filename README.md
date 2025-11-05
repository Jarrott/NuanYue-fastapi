<!-- # Lin-CMS-Flask -->

<h1 align="center">
  <a href="https://doc.cms.talelin.com/">
  <img src="https://up.qi-yue.vip/ny1.png" width="250"/></a>
  <br>
  Pedro-CMS-FastApi
</h1>

<h4 align="center">一个基于FastApi简单易用的CMS后端项目 | <a href="https://doc.cms.talelin.com/" target="_blank">Lin-CMS-Flask</a></h4>

<p align="center">
  <a href="http://Flask.pocoo.org/docs/3.0/" rel="nofollow">
  <img src="https://img.shields.io/badge/Flask-3.1.0-green.svg" alt="Flask version" data-canonical-src="https://img.shields.io/badge/Flask-3.1.0-green.svg" style="max-width:100%;"></a>
    <a href="https://www.python.org/" rel="nofollow">
    <img src="https://img.shields.io/badge/python->=3.9,<3.14-red.svg" alt="Python version" data-canonical-src="https://img.shields.io/badge/python->=3.9,<3.14-red.svg" style="max-width:100%;">
    </a>
      <a href="https://doc.cms.talelin.com/" rel="nofollow"><img src="https://img.shields.io/badge/license-MIT-skyblue.svg" alt="LISENCE" data-canonical-src="https://img.shields.io/badge/license-MIT-skyblue.svg" style="max-width:100%;"></a>
</p>

<blockquote align="center">
（Pedro-CMS-FastApi是借鉴了Lin-CMS的书写风格还有设计哲学进行改造的）Lin-CMS是林间有风团队经过大量项目实践所提炼出的一套<strong>内容管理系统框架</strong>。<br>
 Lin-CMS 可以有效的帮助开发者提高 CMS 的开发效率。
</blockquote>

<p align="center">
  <a href="#简介">简介</a>&nbsp;|&nbsp;<a href="https://doc.cms.talelin.com/start/flask/">快速起步</a>&nbsp;
</p>

## 简介
因为FastApi作为后起之秀，框架的性能更适合现代的开发。

```python
poetry install # 安装依赖

```

## 插件使用
- ServiceManger
`是用此方法来注册RabbitMQ，Redis.....等三方`
```python
# /app/pedro/service_manager.py
```


- RabbitMQ
```python
# 监听MQ任务，功能实现
# app/extensions/rabbitmq/task
# app/extensions/rabbitmq/task/__init__.py 写注册

TASK_HANDLERS = {
    "order_expire": handle_order_timeout,
    "vip_expire": handle_vip_expire,
    "cart_expire": handle_cart_expire,
    # 待加入新的任务
}

# 示例代码(订单下单举例)
    await rds.set(f"order:{order.id}:status", "pending", ex=timedelta(seconds=10))

    # 10s 秒  / m 分 /h 时
    await rabbit.publish_delay(
        message={
            "task_type": "cart_expire",  # 👈 指定任务类型
            "order_id": order.id,
            "user_id": user_id,
            "product_id": product_id},
        delay_ms="10s"
    )

```

- Realtime Database

```python
# 写入信息到RTDB
await rtdb_msg.send_message(admin_id, f"用户 {uid} 下单金额 {amount} 元", extra={"order_id": order_id})

# 读取未读列表
msgs = await rtdb_msg.get_unread(admin_id)

# 全部已读
await rtdb_msg.mark_all_read(admin_id)

```
- Redis

```python
 # redis_keyspace_service.py 主要实现了监听Redis的过期事件
# redis_client 封装的redis链接

# tasks 下是实现业务的，比如监听的key到期后执行什么

TTL_HANDLERS = {
    # 这里根据过期的key来匹配要使用的handler
    "order:": handle_order_expired,
}

```

## 使用cloudflared tunnel代理本地进行远程api测试
```python
# cloudflared tunnel create nuanyue
#  cloudflared tunnel route dns nuanyue api接口地址
#  cloudflared tunnel run nuanyue
# .....细节可以chatgpt 
```