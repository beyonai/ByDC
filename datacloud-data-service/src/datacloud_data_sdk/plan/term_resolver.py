"""TermResolver: 术语标签/名称 → 标准 code 转换。"""
from __future__ import annotations

from typing import Any

from datacloud_data_sdk.ontology.models import OntologyAction
from datacloud_data_sdk.ontology.term_loader import TermLoader
from datacloud_data_sdk.plan.models import ObjectViewField, ObjectViewFunctionParam


class TermResolver:
    """对含 term_set 的参数值进行术语解析。"""

    def __init__(self, term_loader: TermLoader | None = None) -> None:
        self._term_loader = term_loader

    @property
    def term_loader(self) -> TermLoader | None:
        """术语加载器，供 sql_term_resolver 等使用。"""
        return self._term_loader

    def resolve(
        self, action: OntologyAction, params: dict[str, Any]
    ) -> dict[str, Any]:
        """将参数中的标签/别名值解析为标准 code（供 OntologyAction 使用）。"""
        if not self._term_loader:
            return params

        resolved = dict(params)
        for p in action.params:
            if p.term_set and p.param_code in resolved:
                try:
                    value = str(resolved[p.param_code])
                    kw = value if p.term_type == "lookup" else None
                    resolved[p.param_code] = self._term_loader.resolve_code(
                        p.term_set,
                        value,
                        dataset_id=p.dataset_id,
                        term_type_code=p.term_set.split(".")[0] if "." in (p.term_set or "") else None,
                        keyword=kw,
                    )
                except ValueError:
                    pass
        return resolved

    def resolve_params(
        self,
        params: dict[str, Any],
        param_specs: list[ObjectViewFunctionParam],
    ) -> dict[str, Any]:
        """对含 term_set 的参数做名称/标签→code 解析（供 ObjectViewFunctionParam 使用）。"""
        if not self._term_loader:
            return params

        resolved = dict(params)
        for p in param_specs:
            if p.term_set and p.param_code in resolved:
                try:
                    value = str(resolved[p.param_code])
                    kw = value if p.term_type == "lookup" else None
                    resolved[p.param_code] = self._term_loader.resolve_code(
                        p.term_set,
                        value,
                        dataset_id=p.dataset_id,
                        term_type_code=p.term_set.split(".")[0] if "." in (p.term_set or "") else None,
                        keyword=kw,
                    )
                except ValueError:
                    pass
        return resolved

    def resolve_fields(
        self,
        values: dict[str, Any],
        field_specs: list[ObjectViewField],
    ) -> dict[str, Any]:
        """对含 term_set 的 field 做名称/标签→code 解析（供 KB tags 等使用）。"""
        if not self._term_loader:
            return values

        param_specs = [
            ObjectViewFunctionParam(
                param_code=f.name,
                param_name=f.description,
                param_type=f.type,
                direction="IN",
                term_set=f.term_set,
                term_type=f.term_type,
                dataset_id=f.dataset_id,
            )
            for f in field_specs
        ]
        return self.resolve_params(values, param_specs)
