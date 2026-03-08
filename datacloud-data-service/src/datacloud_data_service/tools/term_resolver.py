"""TermResolver: 术语标签 → 标准 code 转换。"""
from __future__ import annotations

from typing import Any

from datacloud_data_sdk.ontology.models import OntologyAction
from datacloud_data_sdk.ontology.term_loader import TermLoader


class TermResolver:
    """对含 term_set 的参数值进行术语解析。"""

    def __init__(self, term_loader: TermLoader | None = None) -> None:
        self._term_loader = term_loader

    def resolve(self, action: OntologyAction, params: dict[str, Any]) -> dict[str, Any]:
        """将参数中的标签/别名值解析为标准 code。"""
        if not self._term_loader:
            return params

        resolved = dict(params)
        for p in action.params:
            if p.term_set and p.param_code in resolved:
                try:
                    resolved[p.param_code] = self._term_loader.resolve_code(
                        p.term_set, str(resolved[p.param_code])
                    )
                except ValueError:
                    pass
        return resolved
