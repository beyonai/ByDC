"""TermResolver: 术语标签/名称 → 标准 code 转换。"""
from __future__ import annotations

from typing import Any

from datacloud_data.ontology.models import OntologyAction, OntologyField
from datacloud_data.ontology.term_loader import TermLoader
from datacloud_data.plan.models import ObjectViewField, ObjectViewFunctionParam


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
            if not p.term_set or p.param_code not in resolved:
                continue
            raw = resolved[p.param_code]
            try:
                # 列表参数：逐项解析为 code 列表
                if isinstance(raw, (list, tuple)):
                    out_list: list[str] = []
                    for v in raw:
                        value = str(v)
                        kw = value if p.term_type == "lookup" else None
                        code = self._term_loader.resolve_code(
                            p.term_set,
                            value,
                            dataset_id=p.dataset_id,
                            term_type_code=p.term_set.split(".")[0]
                            if "." in (p.term_set or "")
                            else None,
                            keyword=kw,
                        )
                        out_list.append(code)
                    resolved[p.param_code] = out_list
                else:
                    value = str(raw)
                    kw = value if p.term_type == "lookup" else None
                    resolved[p.param_code] = self._term_loader.resolve_code(
                        p.term_set,
                        value,
                        dataset_id=p.dataset_id,
                        term_type_code=p.term_set.split(".")[0]
                        if "." in (p.term_set or "")
                        else None,
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
            if not p.term_set or p.param_code not in resolved:
                continue
            raw = resolved[p.param_code]
            try:
                if isinstance(raw, (list, tuple)):
                    out_list: list[str] = []
                    for v in raw:
                        value = str(v)
                        kw = value if p.term_type == "lookup" else None
                        code = self._term_loader.resolve_code(
                            p.term_set,
                            value,
                            dataset_id=p.dataset_id,
                            term_type_code=p.term_set.split(".")[0]
                            if "." in (p.term_set or "")
                            else None,
                            keyword=kw,
                        )
                        out_list.append(code)
                    resolved[p.param_code] = out_list
                else:
                    value = str(raw)
                    kw = value if p.term_type == "lookup" else None
                    resolved[p.param_code] = self._term_loader.resolve_code(
                        p.term_set,
                        value,
                        dataset_id=p.dataset_id,
                        term_type_code=p.term_set.split(".")[0]
                        if "." in (p.term_set or "")
                        else None,
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

    def resolve_filter_values(
        self,
        filters: dict[str, dict[str, Any]],
        fields: list[OntologyField],
    ) -> dict[str, dict[str, Any]]:
        """对 filters 中绑定术语的字段 value 做 label/别名→code 解析。"""
        if not self._term_loader:
            return filters
        if not isinstance(filters, dict):
            return filters

        field_map = {f.field_code: f for f in fields}
        resolved: dict[str, dict[str, Any]] = {}
        for field_code, filter_obj in filters.items():
            resolved[field_code] = dict(filter_obj)
            field = field_map.get(field_code)
            if not field or not field.term_set:
                continue
            op = filter_obj.get("op", "")
            if op in ("is_null", "is_not_null"):
                continue
            value = filter_obj.get("value")
            if value is None:
                continue
            try:
                if isinstance(value, list):
                    resolved[field_code]["value"] = [
                        self._term_loader.resolve_code(
                            field.term_set,
                            str(v),
                            dataset_id=field.dataset_id,
                            term_type_code=field.term_set.split(".")[0] if "." in (field.term_set or "") else None,
                        )
                        for v in value
                    ]
                else:
                    resolved[field_code]["value"] = self._term_loader.resolve_code(
                        field.term_set,
                        str(value),
                        dataset_id=field.dataset_id,
                        term_type_code=field.term_set.split(".")[0] if "." in (field.term_set or "") else None,
                    )
            except ValueError:
                raise
        return resolved
