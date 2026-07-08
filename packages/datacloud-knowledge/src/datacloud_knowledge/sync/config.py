"""TermSyncConfig — 对象级术语同步配置。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TermSyncConfig:
    """对象级术语同步配置（来自 definition.json term_sync 块）。

    term_type_code 不存储在配置中，由 term_type_code(entity_code) 方法自动推导：
        {entity_code}_{term_name_field}
    与 build_terms 对 term_values 字段的命名约定保持一致。
    """

    enabled: bool
    term_name_field: str  # 记录字段名 → term_name，同时用于推导 term_type_code
    term_code_field: str = "id"  # 记录字段名 → term_code，默认主键 id
    term_desc_field: str = ""  # 记录字段名 → term_desc（可选）
    sync_on: list[str] = field(default_factory=lambda: ["insert", "update", "delete"])

    def term_type_code(self, entity_code: str) -> str:
        """自动推导：{entity_code}_{term_name_field}。"""
        return f"{entity_code}_{self.term_name_field}"

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TermSyncConfig:
        """从 definition.json term_sync 块反序列化。"""
        return cls(
            enabled=bool(d.get("enabled", False)),
            term_name_field=str(d["term_name_field"]),
            term_code_field=str(d.get("term_code_field", "id")),
            term_desc_field=str(d.get("term_desc_field", "")),
            sync_on=list(d.get("sync_on", ["insert", "update", "delete"])),
        )

    def to_dict(self) -> dict[str, Any]:
        """序列化为 definition.json term_sync 块。"""
        return {
            "enabled": self.enabled,
            "term_code_field": self.term_code_field,
            "term_name_field": self.term_name_field,
            "term_desc_field": self.term_desc_field,
            "sync_on": list(self.sync_on),
        }
