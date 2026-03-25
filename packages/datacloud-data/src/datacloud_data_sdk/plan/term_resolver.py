"""
术语解析器模块

本模块提供术语解析能力，将业务术语（标签、名称）转换为标准代码。
支持在查询参数中自动解析术语值。

核心功能：
- 解析参数中的术语标签/别名为标准代码
- 支持列表参数的批量解析
- 支持 lookup 类型的关键词搜索

使用示例：
    resolver = TermResolver(term_loader)
    resolved_params = resolver.resolve(action, {"status": "活跃"})
"""

from __future__ import annotations

import logging
from typing import Any

from datacloud_data_sdk.ontology.models import OntologyAction, OntologyField
from datacloud_data_sdk.ontology.term_loader import TermLoader
from datacloud_data_sdk.plan.models import ObjectViewField, ObjectViewFunctionParam

logger = logging.getLogger(__name__)


class TermResolver:
    """
    术语解析器
    
    对包含 term_set 的参数值进行术语解析，将标签/别名转换为标准代码。
    
    Attributes:
        _term_loader: 术语加载器实例
    
    Example:
        resolver = TermResolver(term_loader)
        params = resolver.resolve(action, {"org_type": "总部"})
    """

    def __init__(self, term_loader: TermLoader | None = None) -> None:
        """
        初始化术语解析器
        
        Args:
            term_loader: 术语加载器实例，用于查询术语映射
        """
        self._term_loader = term_loader

    @property
    def term_loader(self) -> TermLoader | None:
        """
        获取术语加载器
        
        Returns:
            TermLoader | None: 术语加载器实例
        """
        return self._term_loader

    def resolve(
        self, action: OntologyAction, params: dict[str, Any]
    ) -> dict[str, Any]:
        """
        解析动作参数中的术语
        
        将参数中的标签/别名值解析为标准 code。
        支持单值和列表值的解析。
        
        Args:
            action: 本体动作定义
            params: 原始参数字典
        
        Returns:
            dict: 解析后的参数字典
        
        Raises:
            TermNotFoundError: 术语不存在
            TermAmbiguousError: 术语匹配到多个结果
        """
        if not self._term_loader:
            return params

        from datacloud_data_sdk.exceptions import TermAmbiguousError, TermNotFoundError

        resolved = dict(params)
        for p in action.params:
            if not p.term_set or p.param_code not in resolved:
                continue
            raw = resolved[p.param_code]
            param_name = p.param_name or p.param_code
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
                            param_name=param_name,
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
                        param_name=param_name,
                    )
            except (TermNotFoundError, TermAmbiguousError):
                raise
            except ValueError as e:
                logger.warning("Term resolution failed for param %s: %s", p.param_code, e)
                raise
        return resolved

    def resolve_params(
        self,
        params: dict[str, Any],
        param_specs: list[ObjectViewFunctionParam],
    ) -> dict[str, Any]:
        """对含 term_set 的参数做名称/标签→code 解析（供 ObjectViewFunctionParam 使用）。
        
        Raises:
            TermNotFoundError: 术语不存在
            TermAmbiguousError: 术语匹配到多个结果
        """
        if not self._term_loader:
            return params

        from datacloud_data_sdk.exceptions import TermAmbiguousError, TermNotFoundError

        resolved = dict(params)
        for p in param_specs:
            if not p.term_set or p.param_code not in resolved:
                continue
            raw = resolved[p.param_code]
            param_name = p.param_name or p.param_code
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
                            param_name=param_name,
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
                        param_name=param_name,
                    )
            except (TermNotFoundError, TermAmbiguousError):
                raise
            except ValueError as e:
                logger.warning("Term resolution failed for param %s: %s", p.param_code, e)
                raise
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
        """对 filters 中绑定术语的字段 value 做 label/别名→code 解析。
        
        Raises:
            TermNotFoundError: 术语不存在
            TermAmbiguousError: 术语匹配到多个结果
        """
        if not self._term_loader:
            return filters
        if not isinstance(filters, dict):
            return filters

        from datacloud_data_sdk.exceptions import TermAmbiguousError, TermNotFoundError

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
            param_name = field.field_name or field.field_code
            try:
                if isinstance(value, list):
                    resolved[field_code]["value"] = [
                        self._term_loader.resolve_code(
                            field.term_set,
                            str(v),
                            dataset_id=field.dataset_id,
                            term_type_code=field.term_set.split(".")[0] if "." in (field.term_set or "") else None,
                            param_name=param_name,
                        )
                        for v in value
                    ]
                else:
                    resolved[field_code]["value"] = self._term_loader.resolve_code(
                        field.term_set,
                        str(value),
                        dataset_id=field.dataset_id,
                        term_type_code=field.term_set.split(".")[0] if "." in (field.term_set or "") else None,
                        param_name=param_name,
                    )
            except (TermNotFoundError, TermAmbiguousError):
                raise
            except ValueError as e:
                logger.warning("Term resolution failed for field %s: %s", field_code, e)
                raise
        return resolved
