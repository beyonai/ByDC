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

from datacloud_data_sdk.ontology.models import OntologyAction
from datacloud_data_sdk.ontology.term_loader import TermLoader
from datacloud_data_sdk.plan.models import ObjectViewField, ObjectViewFunctionParam

logger = logging.getLogger(__name__)


def _should_skip_term_value(value: Any) -> bool:
    """判断值是否应跳过术语转换。"""
    return value is None or (isinstance(value, str) and value.strip() == "")


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

    def _resolve_term_value(
        self,
        *,
        term_set: str,
        term_type: str | None,
        term_field: str | None,
        dataset_id: int | None,
        raw_value: Any,
        param_name: str,
    ) -> Any:
        """将单值或列表术语值解析为标准值。"""
        if not self._term_loader:
            return raw_value

        def _resolve_single(value: Any) -> Any:
            if _should_skip_term_value(value):
                return value
            if isinstance(value, (list, tuple)):
                return [_resolve_single(item) for item in value]
            value_str = str(value)
            keyword = value_str if term_type == "lookup" else None
            return self._term_loader.resolve_value(
                term_set,
                value_str,
                term_field=term_field,
                dataset_id=dataset_id,
                term_type_code=term_set.split(".")[0] if "." in term_set else None,
                keyword=keyword,
                param_name=param_name,
            )

        return _resolve_single(raw_value)

    def resolve(self, action: OntologyAction, params: dict[str, Any]) -> dict[str, Any]:
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
            if _should_skip_term_value(raw):
                # 可选参数未填时 Pydantic 默认置 None，无需 term 解析，与
                # resolve_filter_values 中 `if value is None: return` 行为保持一致
                continue
            param_name = p.param_name or p.param_code
            try:
                if isinstance(raw, (list, tuple)):
                    out_list: list[str] = []
                    for v in raw:
                        out_list.append(
                            self._resolve_term_value(
                                term_set=p.term_set,
                                term_type=p.term_type,
                                term_field=p.term_field,
                                dataset_id=p.dataset_id,
                                raw_value=v,
                                param_name=param_name,
                            )
                        )
                    resolved[p.param_code] = out_list
                else:
                    resolved[p.param_code] = self._resolve_term_value(
                        term_set=p.term_set,
                        term_type=p.term_type,
                        term_field=p.term_field,
                        dataset_id=p.dataset_id,
                        raw_value=raw,
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
        """对含 term_set 的参数做名称/标签→code/name 解析（供 ObjectViewFunctionParam 使用）。

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
            if _should_skip_term_value(raw):
                continue
            param_name = p.param_name or p.param_code
            try:
                if isinstance(raw, (list, tuple)):
                    out_list: list[str] = []
                    for v in raw:
                        out_list.append(
                            self._resolve_term_value(
                                term_set=p.term_set,
                                term_type=p.term_type,
                                term_field=p.term_field,
                                dataset_id=p.dataset_id,
                                raw_value=v,
                                param_name=param_name,
                            )
                        )
                    resolved[p.param_code] = out_list
                else:
                    resolved[p.param_code] = self._resolve_term_value(
                        term_set=p.term_set,
                        term_type=p.term_type,
                        term_field=p.term_field,
                        dataset_id=p.dataset_id,
                        raw_value=raw,
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
        """对含 term_set 的 field 做名称/标签→code/name 解析（供 KB tags 等使用）。"""
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
                term_field=f.term_field,
                dataset_id=f.dataset_id,
            )
            for f in field_specs
        ]
        return self.resolve_params(values, param_specs)

    def resolve_filter_values(
        self,
        filters: Any,
        fields: list[Any],
    ) -> Any:
        """对 filters 中绑定术语的字段 value 做 label/别名→code 解析。

        Raises:
            TermNotFoundError: 术语不存在
            TermAmbiguousError: 术语匹配到多个结果
        """
        if not self._term_loader:
            return filters
        if not isinstance(filters, (dict, list)):
            return filters

        from datacloud_data_sdk.exceptions import TermAmbiguousError, TermNotFoundError

        field_map = {
            getattr(field, "field_code", getattr(field, "property_code", "")): field
            for field in fields
        }

        def _resolve_filter(field_code: str, filter_obj: dict[str, Any]) -> dict[str, Any]:
            resolved_filter = dict(filter_obj)
            field = field_map.get(field_code)
            term_set = getattr(field, "term_set", None) if field is not None else None
            if not field or not term_set:
                return resolved_filter

            op = filter_obj.get("op", "")
            if op not in ("eq", "in"):
                return resolved_filter

            value = filter_obj.get("value")
            if _should_skip_term_value(value):
                return resolved_filter

            param_name = getattr(field, "field_name", None) or getattr(
                field, "property_name", field_code
            )
            try:
                resolved_filter["value"] = self._resolve_term_value(
                    term_set=term_set,
                    term_type=getattr(field, "term_type", None),
                    term_field=getattr(field, "term_field", None),
                    dataset_id=getattr(field, "dataset_id", None),
                    raw_value=value,
                    param_name=param_name,
                )
            except (TermNotFoundError, TermAmbiguousError):
                raise
            except ValueError as e:
                logger.warning("Term resolution failed for field %s: %s", field_code, e)
                raise
            return resolved_filter

        if isinstance(filters, dict):
            return {
                field_code: _resolve_filter(field_code, filter_obj)
                for field_code, filter_obj in filters.items()
            }

        resolved_filters: list[dict[str, Any]] = []
        for item in filters:
            if not isinstance(item, dict):
                resolved_filters.append(item)
                continue
            field_code = str(item.get("field", ""))
            resolved_filters.append(_resolve_filter(field_code, item))
        return resolved_filters
