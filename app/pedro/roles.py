from typing import List, Dict, Iterable
from app.config.settings_manager import get_current_settings

class RoleStore:
    def reload_from_settings(self) -> None:
        s = get_current_settings()
        roles_cfg = getattr(s, "ROLES", None) or {}

        # ✅ 同时兼容 dict 和 Pydantic BaseModel
        if isinstance(roles_cfg, dict):
            hierarchy = roles_cfg.get("hierarchy") or []
            implies = roles_cfg.get("implies") or {}
        else:
            hierarchy = getattr(roles_cfg, "hierarchy", []) or []
            implies = getattr(roles_cfg, "implies", {}) or {}

        # 你的原逻辑
        self._hierarchy = list(hierarchy)
        if self._hierarchy and not implies:
            idx = {r: i for i, r in enumerate(self._hierarchy)}
            implies = {r: {i for i in self._hierarchy[idx[r] + 1:]} for r in self._hierarchy}

        self._hierarchy = hierarchy
        self._implies = implies
        print("✅ RoleStore 已从 settings 重新加载完毕")

role_store = RoleStore()