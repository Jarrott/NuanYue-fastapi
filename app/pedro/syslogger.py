"""
# @Time    : 2025/10/26 4:27
# @Author  : Pedro
# @File    : syslogger.py.py
# @Software: PyCharm
"""
# -*- coding: utf-8 -*-
import logging
from logging.handlers import RotatingFileHandler
from typing import Optional

def setup_logger(name="app", level=logging.INFO, logfile: Optional[str] = None):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    fmt = logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s - %(message)s")

    if not logger.handlers:
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        logger.addHandler(sh)

        if logfile:
            fh = RotatingFileHandler(logfile, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
            fh.setFormatter(fmt)
            logger.addHandler(fh)
    return logger