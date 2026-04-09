"""虚拟动作统一校验器。

在执行前校验输入参数的语义合法性（字段存在性、能力合法性、强制过滤等）。
JSON Schema 结构校验由 MCP inputSchema 负责，此处只做业务规则校验。
"""

from __future__ import annotations

from typing import Any


class VirtualActionValidationError(Exception):
    """虚拟动作校验失败异常。"""

    def __init__(self, message: str, error_code: str = "VIRTUAL_ACTION_ERR_INVALID") -> None:
        super().__init__(message)
        self.error_code = error_code


def _field_map(fields: list[Any]) -> dict[str, Any]:
    """构建字段编码 → 字段元数据的映射（兼容 OntologyField 和 ViewFieldMeta）。"""
    result: dict[str, Any] = {}
    for f in fields:
        fc = f.field_code if hasattr(f, "field_code") else f.property_code
        result[fc] = f
    return result


class VirtualActionValidator:
    """
    虚拟动作输入校验器。

    Usage:
        validator = VirtualActionValidator(fields)
        validator.validate_lookup(arguments)
        validator.validate_analyze(arguments)
    """

    def __init__(self, fields: list[Any]) -> None:
        self._fields = fields
        self._fmap = _field_map(fields)

    def _get_field(self, field_code: str) -> Any:
        f = self._fmap.get(field_code)
        if f is None:
            raise VirtualActionValidationError(
                f"字段 '{field_code}' 不存在",
                "VIRTUAL_ACTION_ERR_UNSUPPORTED_FIELD",
            )
        return f

    def _check_filter_op(self, field_code: str, op: str) -> None:
        f = self._get_field(field_code)
        allowed = getattr(f, "filter_ops", [])
        if allowed and op not in allowed:
            fname = getattr(f, "field_name", None) or getattr(f, "property_name", field_code)
            raise VirtualActionValidationError(
                f"字段 '{fname}'({field_code}) 不支持操作符 '{op}'，允许：{allowed}",
                "VIRTUAL_ACTION_ERR_UNSUPPORTED_OP",
            )

    def _check_required_filters(self, filters: list[dict], required_groups: list[str]) -> None:
        """校验强制过滤字段是否出现在 filters 中。"""
        if "period_required" not in required_groups:
            return
        present_kinds = set()
        for item in filters:
            fc = item.get("field", "")
            f = self._fmap.get(fc)
            if f:
                kind = getattr(f, "analytic_kind", None)
                if kind:
                    present_kinds.add(kind)
        if "period" not in present_kinds:
            raise VirtualActionValidationError(
                "该动作要求在 filters 中提供账期（period）字段过滤条件",
                "VIRTUAL_ACTION_ERR_REQUIRED_FILTER_MISSING",
            )

    def validate_lookup(
        self,
        arguments: dict[str, Any],
        required_filter_groups: list[str] | None = None,
    ) -> None:
        """校验 lookup 动作入参。"""
        # 检查 filters
        for item in arguments.get("filters", []):
            fc = item.get("field", "")
            op = item.get("op", "")
            if fc and op:
                self._check_filter_op(fc, op)
        # 检查 select 字段存在性
        for fc in arguments.get("select", []):
            self._get_field(fc)
        # 强制过滤
        if required_filter_groups:
            self._check_required_filters(arguments.get("filters", []), required_filter_groups)

    def validate_analyze(
        self,
        arguments: dict[str, Any],
        required_filter_groups: list[str] | None = None,
    ) -> None:
        """校验 analyze 动作入参。"""
        dimensions = arguments.get("dimensions", [])
        metrics = arguments.get("metrics", [])

        # metrics 不能为空
        if not metrics:
            raise VirtualActionValidationError(
                "analyze 动作 metrics 不能为空，若只需明细请使用 lookup",
                "VIRTUAL_ACTION_ERR_UNSUPPORTED_FIELD",
            )

        # 校验维度
        for dim in dimensions:
            fc = dim.get("field", "")
            group_op = dim.get("group_op", "")
            f = self._get_field(fc)
            allowed_gops = getattr(f, "group_ops", [])
            if allowed_gops and group_op not in allowed_gops:
                fname = getattr(f, "field_name", None) or getattr(f, "property_name", fc)
                raise VirtualActionValidationError(
                    f"字段 '{fname}'({fc}) 不支持分组方式 '{group_op}'，允许：{allowed_gops}",
                    "VIRTUAL_ACTION_ERR_UNSUPPORTED_OP",
                )
            # range 必须携带 buckets
            if group_op == "range" and not dim.get("buckets"):
                raise VirtualActionValidationError(
                    f"字段 '{fc}' 使用 range 分组时必须提供 buckets 数组",
                    "VIRTUAL_ACTION_ERR_UNSUPPORTED_OP",
                )

        # 收集 metrics.as 别名，供 having 引用校验
        metric_aliases: set[str] = set()
        for mtr in metrics:
            if mtr.get("agg") == "count_all":
                alias = mtr.get("as", "")
                if alias:
                    metric_aliases.add(alias)
                continue
            fc = mtr.get("field", "")
            agg = mtr.get("agg", "")
            f = self._get_field(fc)
            allowed_aggs = getattr(f, "aggregate_ops", [])
            if allowed_aggs and agg not in allowed_aggs:
                fname = getattr(f, "field_name", None) or getattr(f, "property_name", fc)
                raise VirtualActionValidationError(
                    f"字段 '{fname}'({fc}) 不支持聚合函数 '{agg}'，允许：{allowed_aggs}",
                    "VIRTUAL_ACTION_ERR_UNSUPPORTED_OP",
                )
            alias = mtr.get("as", "")
            if alias:
                metric_aliases.add(alias)

        # 校验 having.field 必须是 metrics.as 别名
        for hav in arguments.get("having", []):
            hfield = hav.get("field", "")
            if hfield and hfield not in metric_aliases:
                raise VirtualActionValidationError(
                    f"having.field '{hfield}' 必须是 metrics 中某项的 as 别名，当前别名：{metric_aliases}",
                    "VIRTUAL_ACTION_ERR_UNSUPPORTED_FIELD",
                )

        # 校验 filters
        for item in arguments.get("filters", []):
            fc = item.get("field", "")
            op = item.get("op", "")
            if fc and op:
                self._check_filter_op(fc, op)

        # 强制过滤
        if required_filter_groups:
            self._check_required_filters(arguments.get("filters", []), required_filter_groups)
