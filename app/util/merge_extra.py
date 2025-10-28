# app/util/merge_extra_utils.py
from copy import deepcopy
from sqlalchemy.orm.attributes import flag_modified

_SENTINEL = object()

def merge_extra(
    target_obj,
    key: str = "extra",
    default: dict | None = None,
    *,
    fill_none: bool = False,
    list_strategy: str = "keep_current",
) -> None:
    """
    智能合并 ORM 对象的 JSON 字段（用于 FastAPI + SQLAlchemy）
    - default: 新版系统定义的默认字段结构
    - fill_none: 是否用 default 填充 None
    - list_strategy: 列表合并策略
    """

    current = getattr(target_obj, key, None) or {}
    merged = _deep_merge(default, current, fill_none=fill_none, list_strategy=list_strategy)
    setattr(target_obj, key, merged)
    flag_modified(target_obj, key)  # ✅ 通知 SQLAlchemy 字段更新


def _deep_merge(default: dict | None, current: dict | None, *, fill_none=False, list_strategy="keep_current") -> dict:
    if default is None and current is None:
        return {}
    if default is None:
        return deepcopy(current) if current is not None else {}
    if current is None:
        return deepcopy(default)

    if isinstance(default, dict) and isinstance(current, dict):
        out = {}
        for key in set(default.keys()) | set(current.keys()):
            dv = default.get(key, _SENTINEL)
            cv = current.get(key, _SENTINEL)
            if cv is _SENTINEL:
                out[key] = deepcopy(dv)
                continue
            if dv is _SENTINEL:
                out[key] = deepcopy(cv)
                continue
            if isinstance(dv, dict) and isinstance(cv, dict):
                out[key] = _deep_merge(dv, cv, fill_none=fill_none, list_strategy=list_strategy)
            elif isinstance(dv, list) and isinstance(cv, list):
                if list_strategy == "concat":
                    out[key] = cv + [x for x in dv if x not in cv]
                elif list_strategy == "default_if_empty":
                    out[key] = cv if len(cv) else deepcopy(dv)
                elif list_strategy == "keep_default":
                    out[key] = deepcopy(dv)
                else:
                    out[key] = deepcopy(cv)
            else:
                if cv is None and fill_none:
                    out[key] = deepcopy(dv)
                else:
                    out[key] = deepcopy(cv)
        return out
    if current is None and fill_none:
        return deepcopy(default)
    return deepcopy(current)
