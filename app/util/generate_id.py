# -*- coding: utf-8 -*-
"""
# @Time    : 2025/11/12 22:30
# @Author  : Pedro
# @File    : id_generator.py
# @Software: PyCharm
"""

import time
import threading

class SnowflakeGenerator:
    """
    🚀 Pedro-Core 分布式唯一ID生成器 (Snowflake)
    64bit结构：
    1bit符号位 + 41bit时间戳 + 10bit机器号 + 12bit序列号
    """
    def __init__(self, worker_id: int = 1, datacenter_id: int = 1):
        # 位长度
        self.worker_id_bits = 5
        self.datacenter_id_bits = 5
        self.sequence_bits = 12

        # 最大取值
        self.max_worker_id = -1 ^ (-1 << self.worker_id_bits)  # 31
        self.max_datacenter_id = -1 ^ (-1 << self.datacenter_id_bits)  # 31

        # 位移偏移
        self.worker_id_shift = self.sequence_bits
        self.datacenter_id_shift = self.sequence_bits + self.worker_id_bits
        self.timestamp_left_shift = self.sequence_bits + self.worker_id_bits + self.datacenter_id_bits

        # 序列掩码
        self.sequence_mask = -1 ^ (-1 << self.sequence_bits)

        # 时间起点（可固定为项目上线时间）
        self.twepoch = 1700000000000  # 2023-11 起始毫秒时间戳

        # 初始化
        self.worker_id = worker_id
        self.datacenter_id = datacenter_id
        self.sequence = 0
        self.last_timestamp = -1

        self.lock = threading.Lock()

    def _timestamp(self):
        return int(time.time() * 1000)

    def _wait_next_millis(self, last_timestamp):
        ts = self._timestamp()
        while ts <= last_timestamp:
            ts = self._timestamp()
        return ts

    def generate_id(self) -> int:
        with self.lock:
            timestamp = self._timestamp()

            if timestamp < self.last_timestamp:
                raise Exception("时钟回拨错误，系统时间倒退")

            if timestamp == self.last_timestamp:
                self.sequence = (self.sequence + 1) & self.sequence_mask
                if self.sequence == 0:
                    timestamp = self._wait_next_millis(self.last_timestamp)
            else:
                self.sequence = 0

            self.last_timestamp = timestamp

            new_id = (
                ((timestamp - self.twepoch) << self.timestamp_left_shift)
                | (self.datacenter_id << self.datacenter_id_shift)
                | (self.worker_id << self.worker_id_shift)
                | self.sequence
            )
            return new_id


# ✅ 初始化全局生成器
snowflake = SnowflakeGenerator(worker_id=1, datacenter_id=1)
new_id = snowflake.generate_id()
