"""
# @Time    : 2025/10/28 1:39
# @Author  : Pedro
# @File    : parser.py
# @Software: PyCharm
"""


def deep_merge_dict(base: dict, override: dict) -> dict:
    result = base.copy()
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = deep_merge_dict(result[k], v)
        else:
            result[k] = v
    return result


def normalize_keys(d: dict) -> dict:
    res = {}
    for k, v in d.items():
        if isinstance(v, dict):
            v = normalize_keys(v)
        res[k.lower()] = v
        res[k.upper()] = v
    return res
