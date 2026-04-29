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


# 不允许出现在 dimensions 中的 analytic_kind（指标分类）
_METRIC_KINDS: frozenset[str] = frozenset(
    {"basic_metric", "snapshot_metric", "derived_metric", "formula_metric"}
)


def _field_map(fields: list[Any]) -> dict[str, Any]:
    """构建字段编码 → 字段元数据的映射（兼容 OntologyField 和 ViewFieldMeta）。"""
    result: dict[str, Any] = {}
    for f in fields:
        fc = f.field_code if hasattr(f, "field_code") else f.property_code
        result[fc] = f
    return result


def _list_or_empty(arguments: dict[str, Any], key: str) -> list[Any]:
    """读取 ``arguments[key]``；缺失或为 ``None`` 时返回空列表。

    注意：``dict.get(key, [])`` 在键存在且值为 ``None``（如 JSON null）时仍返回 ``None``，
    会导致 ``for x in ...`` 触发 ``TypeError``。
    """

    val = arguments.get(key)
    return val if isinstance(val, list) else []


def _coerce_metric_agg_from_func(mtr: dict[str, Any]) -> None:
    """若 ``agg`` 缺失但存在 ``func``，将后者写入 ``agg`` 并移除 ``func``。

    协议 §3.2.3 规定键名为 ``agg``；部分模型误用 ``func``，会导致校验读到空聚合。
    原地修改 ``mtr``。
    """

    raw_agg = mtr.get("agg")
    if isinstance(raw_agg, str) and raw_agg.strip():
        return
    func_val = mtr.get("func")
    if isinstance(func_val, str) and func_val.strip():
        mtr["agg"] = func_val.strip()
        mtr.pop("func", None)


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

    def _check_linked(self, field_code: str) -> None:
        """若字段为 linked 类型则报错。"""
        f = self._get_field(field_code)
        if getattr(f, "property_kind", "physical") == "linked":
            fname = getattr(f, "field_name", None) or field_code
            raise VirtualActionValidationError(
                f"字段 '{fname}' 为跨表关联字段，暂不支持，请使用对应的视图对象查询",
                "VIRTUAL_ACTION_ERR_LINKED_NOT_SUPPORTED",
            )

    def validate_query(
        self,
        arguments: dict[str, Any],
        required_filter_groups: list[str] | None = None,
    ) -> None:
        """校验 query_ontology 动作入参（明细查询）。

        在 validate_lookup 基础上增加：
        1. select / filters / order_by 中的 linked 字段检测
        2. filter_relation=OR + period_required 冲突检测
        """
        filter_relation = (arguments.get("filter_relation") or "AND").upper()

        # OR + period_required 冲突：账期强制要求与 OR 连接语义矛盾
        if (
            filter_relation == "OR"
            and required_filter_groups
            and "period_required" in required_filter_groups
        ):
            raise VirtualActionValidationError(
                "该对象含账期强制约束，不允许使用 filter_relation=OR，"
                "OR 连接会使账期条件失去强制约束效果",
                "VIRTUAL_ACTION_ERR_INVALID",
            )

        # 检查 select 字段：存在性 + linked 拦截
        for fc in _list_or_empty(arguments, "select"):
            self._check_linked(fc)

        # 检查 filters：存在性 + linked 拦截 + op 合法性
        for item in _list_or_empty(arguments, "filters"):
            fc = item.get("field", "")
            op = item.get("op", "")
            if fc:
                self._check_linked(fc)
            if fc and op:
                self._check_filter_op(fc, op)

        # 检查 order_by 字段：存在性 + linked 拦截
        for ob in _list_or_empty(arguments, "order_by"):
            fc = ob.get("field", "")
            if fc:
                self._check_linked(fc)

        # 强制过滤（在 OR 冲突检测通过后才到这里，即 filter_relation=AND）
        if required_filter_groups:
            self._check_required_filters(
                _list_or_empty(arguments, "filters"), required_filter_groups
            )

    def validate_lookup(
        self,
        arguments: dict[str, Any],
        required_filter_groups: list[str] | None = None,
    ) -> None:
        """校验 lookup 动作入参。"""
        # 检查 filters
        for item in _list_or_empty(arguments, "filters"):
            fc = item.get("field", "")
            op = item.get("op", "")
            if fc and op:
                self._check_filter_op(fc, op)
        # 检查 select 字段存在性
        for fc in _list_or_empty(arguments, "select"):
            self._get_field(fc)
        # 强制过滤
        if required_filter_groups:
            self._check_required_filters(
                _list_or_empty(arguments, "filters"), required_filter_groups
            )

    def validate_analyze(
        self,
        arguments: dict[str, Any],
        required_filter_groups: list[str] | None = None,
    ) -> None:
        """校验 analyze 动作入参。"""
        dimensions = _list_or_empty(arguments, "dimensions")
        metrics = _list_or_empty(arguments, "metrics")

        # metrics 不能为空
        if not metrics:
            raise VirtualActionValidationError(
                "analyze 动作 metrics 不能为空，若只需明细请使用 query",
                "VIRTUAL_ACTION_ERR_UNSUPPORTED_FIELD",
            )

        # 校验维度
        for dim in dimensions:
            if isinstance(dim, str):
                dim = {"field": dim}
            fc = dim.get("field", "")
            f = self._get_field(fc)

            # 指标类字段不允许作为分组维度（range 区间分桶除外：将指标转为分类维度）
            analytic_kind = getattr(f, "analytic_kind", None)
            if analytic_kind in _METRIC_KINDS and dim.get("group_op", "self") != "range":
                fname = getattr(f, "field_name", None) or getattr(f, "property_name", fc)
                raise VirtualActionValidationError(
                    f"字段 '{fname}'({fc}) 是指标类型（{analytic_kind}），"
                    "不能作为分组维度（仅支持 group_op=range 区间分桶），"
                    "请将其放入 metrics",
                    "VIRTUAL_ACTION_ERR_UNSUPPORTED_OP",
                )

            allowed_gops = getattr(f, "group_ops", [])
            # group_op 未传时跳过校验（不约束分组方式）
            if "group_op" not in dim:
                continue
            group_op = dim["group_op"]
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
            if isinstance(mtr, dict):
                _coerce_metric_agg_from_func(mtr)
            if not isinstance(mtr, dict):
                continue
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
        for hav in _list_or_empty(arguments, "having"):
            hfield = hav.get("field", "")
            if hfield and hfield not in metric_aliases:
                raise VirtualActionValidationError(
                    f"having.field '{hfield}' 必须是 metrics 中某项的 as 别名，当前别名：{metric_aliases}",
                    "VIRTUAL_ACTION_ERR_UNSUPPORTED_FIELD",
                )

        # 校验 filters
        for item in _list_or_empty(arguments, "filters"):
            fc = item.get("field", "")
            op = item.get("op", "")
            if fc and op:
                self._check_filter_op(fc, op)

        # 强制过滤
        if required_filter_groups:
            self._check_required_filters(
                _list_or_empty(arguments, "filters"), required_filter_groups
            )
