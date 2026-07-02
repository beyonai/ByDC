"""查询条件构造器 — QueryWrapper 与 AggWrapper。

这两个类作为公共工具注入 Action 脚本命名空间（Q / A），脚本无需 import 直接使用。
调试环境（DebugLoader）和正式执行环境（ScriptExecutor）均通过此模块获取实现。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

# ── QueryWrapper ──────────────────────────────────────────────────────────────


class QueryWrapper:
    """链式条件构造器，与 MyBatis-Plus QueryWrapper 对标。

    每次 chaining 返回新实例，安全地支持多个查询并发构建。

    示例::

        rows = await travel_application_mapper.select(
            Q.eq(TravelApplication.F.status, "草稿")
             .gte(TravelApplication.F.total_amount, 1000)
             .order_by(TravelApplication.F.submit_time, desc=True)
             .page(1, 20)
        )
    """

    def __init__(self) -> None:
        self._conditions: list[tuple[Any, ...]] = []
        self._order_fields: list[tuple[str, bool]] = []
        self._page_num: int = 1
        self._page_size: int | None = None
        self._limit_n: int | None = None

    def _clone(self) -> QueryWrapper:
        q = QueryWrapper()
        q._conditions = list(self._conditions)
        q._order_fields = list(self._order_fields)
        q._page_num = self._page_num
        q._page_size = self._page_size
        q._limit_n = self._limit_n
        return q

    def eq(self, field: str, value: Any) -> QueryWrapper:
        q = self._clone()
        q._conditions.append(("eq", field, value))
        return q

    def ne(self, field: str, value: Any) -> QueryWrapper:
        q = self._clone()
        q._conditions.append(("ne", field, value))
        return q

    def gt(self, field: str, value: Any) -> QueryWrapper:
        q = self._clone()
        q._conditions.append(("gt", field, value))
        return q

    def gte(self, field: str, value: Any) -> QueryWrapper:
        q = self._clone()
        q._conditions.append(("gte", field, value))
        return q

    def lt(self, field: str, value: Any) -> QueryWrapper:
        q = self._clone()
        q._conditions.append(("lt", field, value))
        return q

    def lte(self, field: str, value: Any) -> QueryWrapper:
        q = self._clone()
        q._conditions.append(("lte", field, value))
        return q

    def like(self, field: str, pattern: str) -> QueryWrapper:
        q = self._clone()
        q._conditions.append(("like", field, f"%{pattern}%"))
        return q

    def in_(self, field: str, values: list[Any]) -> QueryWrapper:
        q = self._clone()
        q._conditions.append(("in", field, values))
        return q

    def is_null(self, field: str) -> QueryWrapper:
        q = self._clone()
        q._conditions.append(("is_null", field))
        return q

    def is_not_null(self, field: str) -> QueryWrapper:
        q = self._clone()
        q._conditions.append(("is_not_null", field))
        return q

    def order_by(self, field: str, desc: bool = False) -> QueryWrapper:
        q = self._clone()
        q._order_fields = list(self._order_fields) + [(field, desc)]
        return q

    def page(self, page: int, page_size: int = 20) -> QueryWrapper:
        q = self._clone()
        q._page_num = page
        q._page_size = page_size
        return q

    def limit(self, n: int) -> QueryWrapper:
        q = self._clone()
        q._limit_n = n
        return q

    def to_where_sql(self) -> tuple[str, list[Any]]:
        """转换为 SQL WHERE 子句和参数列表（SQLite 风格，供 DebugLoader 使用）。"""
        parts: list[str] = []
        params: list[Any] = []
        op_map = {
            "eq": "= ?",
            "ne": "!= ?",
            "gt": "> ?",
            "gte": ">= ?",
            "lt": "< ?",
            "lte": "<= ?",
            "like": "LIKE ?",
        }
        for cond in self._conditions:
            op = cond[0]
            if op in op_map:
                _, field, value = cond
                parts.append(f"{field} {op_map[op]}")
                params.append(value)
            elif op == "in":
                _, field, values = cond
                placeholders = ", ".join("?" * len(values))
                parts.append(f"{field} IN ({placeholders})")
                params.extend(values)
            elif op == "is_null":
                _, field = cond
                parts.append(f"{field} IS NULL")
            elif op == "is_not_null":
                _, field = cond
                parts.append(f"{field} IS NOT NULL")
        where = " AND ".join(parts) if parts else "1=1"
        return where, params

    def to_filters(self) -> dict[str, Any]:
        """转换为 DynamicQueryExecutor 的 filters 格式 {field: {op, value}}。"""
        filters: dict[str, Any] = {}
        for cond in self._conditions:
            op = cond[0]
            if op in ("eq", "ne", "gt", "gte", "lt", "lte", "like"):
                _, field, value = cond
                filters[field] = {"op": op, "value": value}
            elif op == "in":
                _, field, values = cond
                filters[field] = {"op": "in", "value": values}
            elif op == "is_null":
                _, field = cond
                filters[field] = {"op": "is_null"}
            elif op == "is_not_null":
                _, field = cond
                filters[field] = {"op": "is_not_null"}
        return filters

    def to_payload(self) -> dict[str, Any]:
        """内部序列化格式，供 DebugLoader 使用。"""
        return {
            "_wrapper_type": "query",
            "conditions": [list(c) for c in self._conditions],
            "order_by": self._order_fields,
            "page": self._page_num,
            "page_size": self._page_size,
            "limit": self._limit_n,
        }


# ── AggWrapper ────────────────────────────────────────────────────────────────


class AggWrapper:
    """链式聚合构造器。

    示例::

        result = await travel_expense_mapper.agg(
            A.sum("amount").count("id", as_="count")
             .group_by("expense_type")
             .where(Q.eq("app_id", params["app_id"]))
        )
    """

    def __init__(self) -> None:
        self._aggregates: list[dict[str, str]] = []
        self._group_fields: list[str] = []
        self._where_wrapper: QueryWrapper | None = None
        self._order_fields: list[tuple[str, bool]] = []
        self._limit_n: int | None = None

    def _clone(self) -> AggWrapper:
        a = AggWrapper()
        a._aggregates = deepcopy(self._aggregates)
        a._group_fields = list(self._group_fields)
        a._where_wrapper = self._where_wrapper
        a._order_fields = list(self._order_fields)
        a._limit_n = self._limit_n
        return a

    def _add_agg(self, func: str, field: str, as_: str | None) -> AggWrapper:
        a = self._clone()
        alias = as_ or field
        a._aggregates = list(self._aggregates) + [{"func": func, "field": field, "as": alias}]
        return a

    def count(self, field: str = "id", as_: str | None = None) -> AggWrapper:
        return self._add_agg("COUNT", field, as_ or f"count_{field}")

    def sum(self, field: str, as_: str | None = None) -> AggWrapper:
        return self._add_agg("SUM", field, as_ or field)

    def avg(self, field: str, as_: str | None = None) -> AggWrapper:
        return self._add_agg("AVG", field, as_ or field)

    def max(self, field: str, as_: str | None = None) -> AggWrapper:
        return self._add_agg("MAX", field, as_ or field)

    def min(self, field: str, as_: str | None = None) -> AggWrapper:
        return self._add_agg("MIN", field, as_ or field)

    def group_by(self, *fields: str) -> AggWrapper:
        a = self._clone()
        a._group_fields = list(self._group_fields) + list(fields)
        return a

    def where(self, wrapper: QueryWrapper) -> AggWrapper:
        a = self._clone()
        a._where_wrapper = wrapper
        return a

    def order_by(self, field: str, desc: bool = False) -> AggWrapper:
        a = self._clone()
        a._order_fields = list(self._order_fields) + [(field, desc)]
        return a

    def limit(self, n: int) -> AggWrapper:
        a = self._clone()
        a._limit_n = n
        return a

    def to_payload(self) -> dict[str, Any]:
        """内部序列化格式，供 DebugLoader 使用。"""
        return {
            "_wrapper_type": "agg",
            "aggregates": self._aggregates,
            "group_by": self._group_fields,
            "where": self._where_wrapper.to_payload() if self._where_wrapper else None,
            "order_by": self._order_fields,
            "limit": self._limit_n,
        }
