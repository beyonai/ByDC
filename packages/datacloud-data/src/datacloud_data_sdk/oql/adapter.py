"""
OQL 原子翻译层 + 策略 A 执行器

职责：
1. 原子翻译层函数：resolve_object, resolve_column, build_field_map, translate_conditions 等
2. 策略 A 执行器：OqlAdapter 类，将 OQL 参数翻译为 SqlExecTask / ApiExecTask
"""

from __future__ import annotations
import logging
from typing import Any, Optional
from datetime import datetime, timedelta
import re
import sys

if sys.version_info >= (3, 8):
    from typing import Literal
else:
    from typing_extensions import Literal

from datacloud_data_sdk.executor.models import SqlExecTask, ApiExecTask
from datacloud_data_sdk.oql.models import OQLError, OQLErrorCode

logger = logging.getLogger(__name__)


# ============================================================================
# 原子翻译层函数
# ============================================================================

def resolve_object(object_code: str, registry) -> Any:
    """
    从本体注册表解析对象。

    Args:
        object_code: 对象代码
        registry: 本体注册表

    Returns:
        OntologyClass 对象

    Raises:
        OQLError: 对象不存在
    """
    try:
        cls = registry.get_class(object_code)
        if cls is None:
            raise OQLError(
                OQLErrorCode.OQL_ERR_UNKNOWN_OBJECT,
                f"对象 '{object_code}' 不存在"
            )
        return cls
    except Exception as e:
        if isinstance(e, OQLError):
            raise
        raise OQLError(
            OQLErrorCode.OQL_ERR_UNKNOWN_OBJECT,
            f"对象 '{object_code}' 解析失败：{str(e)}"
        )


def resolve_column(field_code: str, cls: Any, db_type: str) -> str:
    """
    解析字段为数据库列名（三级回退）。

    Level 1: physical_mappings[db_type] → source_ref
    Level 2: source_column (if not None)
    Level 3: field_code (100% 成功)

    Args:
        field_code: 字段代码
        cls: OntologyClass 对象
        db_type: 数据库类型

    Returns:
        数据库列名

    Raises:
        OQLError: 字段不存在
    """
    field = None
    for f in cls.fields:
        if f.field_code == field_code:
            field = f
            break

    if field is None:
        raise OQLError(
            OQLErrorCode.OQL_ERR_UNKNOWN_FIELD,
            f"对象 '{cls.object_code}' 中字段 '{field_code}' 不存在"
        )

    # Level 1: physical_mappings
    if hasattr(field, 'physical_mappings') and field.physical_mappings:
        mapping = field.physical_mappings.get(db_type.upper())
        if mapping and mapping.get('source_ref'):
            return mapping['source_ref']

    # Level 2: source_column
    if hasattr(field, 'source_column') and field.source_column:
        return field.source_column

    # Level 3: field_code
    return field_code


def build_field_map(cls: Any, field_codes: list[str], db_type: str) -> dict[str, str]:
    """
    构建字段映射表 {field_code: column_name}。

    Args:
        cls: OntologyClass 对象
        field_codes: 字段代码列表
        db_type: 数据库类型

    Returns:
        字段映射字典
    """
    field_map = {}
    for field_code in field_codes:
        try:
            field_map[field_code] = resolve_column(field_code, cls, db_type)
        except OQLError:
            # 字段不存在，跳过（后续会在 translate_conditions 中报错）
            pass
    return field_map


def get_quoting(db_type: str) -> str:
    """获取 SQL 引号字符。"""
    db_type_upper = db_type.upper()
    if db_type_upper in ("MYSQL", "MARIADB"):
        return "`"
    elif db_type_upper in ("POSTGRESQL", "CLICKHOUSE"):
        return '"'
    elif db_type_upper == "HIVE":
        return "`"
    else:
        return '"'


def inline_value(value: Any) -> str:
    """
    将值内联为 SQL 字面量（用于 Hive 等不支持参数化的方言）。

    Args:
        value: Python 值

    Returns:
        SQL 字面量字符串
    """
    if value is None:
        return "NULL"
    elif isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    elif isinstance(value, (int, float)):
        return str(value)
    elif isinstance(value, str):
        # 转义单引号
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    elif isinstance(value, (list, tuple)):
        return f"({', '.join(inline_value(v) for v in value)})"
    else:
        return f"'{str(value)}'"


def expand_relative_date(expr: str) -> tuple[str, str]:
    """
    展开相对日期表达式为绝对时间区间。

    支持格式：
    - "today" → [今天 00:00, 今天 23:59:59]
    - "yesterday" → [昨天 00:00, 昨天 23:59:59]
    - "this_week" → [本周一 00:00, 本周日 23:59:59]
    - "this_month" → [本月 1 日 00:00, 本月最后一天 23:59:59]
    - "last_7_days" → [7 天前 00:00, 今天 23:59:59]
    - "last_30_days" → [30 天前 00:00, 今天 23:59:59]

    Args:
        expr: 相对日期表达式

    Returns:
        (start_datetime, end_datetime) 元组，格式为 ISO 8601 字符串
    """
    now = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if expr == "today":
        start = today
        end = today.replace(hour=23, minute=59, second=59)
    elif expr == "yesterday":
        yesterday = today - timedelta(days=1)
        start = yesterday
        end = yesterday.replace(hour=23, minute=59, second=59)
    elif expr == "this_week":
        # 周一为一周开始
        days_since_monday = today.weekday()
        start = today - timedelta(days=days_since_monday)
        end = start + timedelta(days=6)
        end = end.replace(hour=23, minute=59, second=59)
    elif expr == "this_month":
        start = today.replace(day=1)
        if today.month == 12:
            end = start.replace(year=start.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end = start.replace(month=start.month + 1, day=1) - timedelta(days=1)
        end = end.replace(hour=23, minute=59, second=59)
    elif expr == "last_7_days":
        start = today - timedelta(days=7)
        end = today.replace(hour=23, minute=59, second=59)
    elif expr == "last_30_days":
        start = today - timedelta(days=30)
        end = today.replace(hour=23, minute=59, second=59)
    else:
        raise OQLError(
            OQLErrorCode.OQL_ERR_INVALID_OPERATOR,
            f"不支持的相对日期表达式：{expr}"
        )

    return (start.isoformat(), end.isoformat())


def translate_simple_condition(
    cond: dict,
    field_map: dict[str, str],
    db_type: str,
    params: list,
    quoting: str = '"',
    is_having: bool = False
) -> str:
    """
    翻译单个条件为 SQL 片段。

    Args:
        cond: 条件字典 {field, op, value}
        field_map: 字段映射表
        db_type: 数据库类型
        params: 参数列表（会被修改）
        quoting: SQL 引号字符
        is_having: 是否为 HAVING 条件

    Returns:
        SQL 条件片段
    """
    field = cond["field"]
    op = cond["op"]
    value = cond.get("value")

    if field not in field_map and not is_having:
        raise OQLError(
            OQLErrorCode.OQL_ERR_UNKNOWN_FIELD,
            f"字段 '{field}' 不存在"
        )

    col_expr = field if is_having else f"{quoting}{field_map[field]}{quoting}"
    ph = "?" if db_type.upper() != "HIVE" else None

    if op == "eq":
        params.append(value)
        return f"{col_expr} = {ph or inline_value(value)}"
    elif op == "ne":
        params.append(value)
        return f"{col_expr} <> {ph or inline_value(value)}"
    elif op in ("gt", "gte", "lt", "lte"):
        sym = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[op]
        params.append(value)
        return f"{col_expr} {sym} {ph or inline_value(value)}"
    elif op == "in":
        if not value:
            return "1=0"
        phs = ", ".join(ph or inline_value(v) for v in value)
        if ph:
            params.extend(value)
        return f"{col_expr} IN ({phs})"
    elif op == "nin":
        if not value:
            return "1=1"
        phs = ", ".join(ph or inline_value(v) for v in value)
        if ph:
            params.extend(value)
        return f"{col_expr} NOT IN ({phs})"
    elif op == "like":
        params.append(value)
        return f"{col_expr} LIKE {ph or inline_value(value)}"
    elif op == "isNull":
        return f"{col_expr} IS NULL" if value else f"{col_expr} IS NOT NULL"
    elif op == "between":
        lo, hi = value[0], value[1]
        if ph:
            params.extend([lo, hi])
            return f"{col_expr} BETWEEN ? AND ?"
        return f"{col_expr} BETWEEN {inline_value(lo)} AND {inline_value(hi)}"
    elif op == "relativeDate":
        start, end = expand_relative_date(value)
        if ph:
            params.extend([start, end])
            return f"{col_expr} BETWEEN ? AND ?"
        return f"{col_expr} BETWEEN {inline_value(start)} AND {inline_value(end)}"
    else:
        raise OQLError(
            OQLErrorCode.OQL_ERR_INVALID_OPERATOR,
            f"不支持的操作符：{op}"
        )


def translate_logic_condition(
    cond: dict,
    field_map: dict[str, str],
    db_type: str,
    params: list,
    quoting: str = '"',
    is_having: bool = False
) -> str:
    """
    翻译逻辑条件（OR / NOT）为 SQL 片段。

    Args:
        cond: 逻辑条件字典 {logic, conditions|condition}
        field_map: 字段映射表
        db_type: 数据库类型
        params: 参数列表
        quoting: SQL 引号字符
        is_having: 是否为 HAVING 条件

    Returns:
        SQL 条件片段
    """
    logic = cond.get("logic")

    if logic == "or":
        conditions = cond.get("conditions", [])
        parts = []
        for c in conditions:
            if "logic" in c:
                parts.append(translate_logic_condition(c, field_map, db_type, params, quoting, is_having))
            else:
                parts.append(translate_simple_condition(c, field_map, db_type, params, quoting, is_having))
        return " OR ".join(f"({p})" for p in parts)
    elif logic == "not":
        inner_cond = cond.get("condition")
        if "logic" in inner_cond:
            inner_sql = translate_logic_condition(inner_cond, field_map, db_type, params, quoting, is_having)
        else:
            inner_sql = translate_simple_condition(inner_cond, field_map, db_type, params, quoting, is_having)
        return f"NOT ({inner_sql})"
    else:
        raise OQLError(
            OQLErrorCode.OQL_ERR_INVALID_OPERATOR,
            f"不支持的逻辑操作符：{logic}"
        )


def translate_conditions(
    conditions: list[dict],
    field_map: dict[str, str],
    db_type: str,
    params: list,
    quoting: str = '"',
    is_having: bool = False
) -> str:
    """
    翻译条件数组为 SQL 片段（不含 WHERE 关键字）。

    根节点条件间默认 AND。

    Args:
        conditions: 条件列表
        field_map: 字段映射表
        db_type: 数据库类型
        params: 参数列表
        quoting: SQL 引号字符
        is_having: 是否为 HAVING 条件

    Returns:
        SQL 条件片段
    """
    parts = []
    for cond in conditions:
        if "logic" in cond:
            parts.append(translate_logic_condition(cond, field_map, db_type, params, quoting, is_having))
        else:
            parts.append(translate_simple_condition(cond, field_map, db_type, params, quoting, is_having))
    return " AND ".join(f"({p})" for p in parts)


def resolve_table(cls: Any) -> str:
    """获取对象对应的表名。"""
    if hasattr(cls, 'table_name') and cls.table_name:
        return cls.table_name
    return cls.object_code


def build_limit_clause(limit: int, offset: Optional[int], db_type: str) -> str:
    """
    构建 LIMIT 子句。

    Args:
        limit: 限制行数
        offset: 偏移量
        db_type: 数据库类型

    Returns:
        LIMIT 子句字符串
    """
    db_type_upper = db_type.upper()

    # Hive 不支持 OFFSET，仅支持 LIMIT
    if db_type_upper == "HIVE":
        if offset and offset > 0:
            logger.warning("Hive 不支持 OFFSET，已忽略 offset=%d", offset)
        return f"LIMIT {limit}"

    # 其他数据库支持 LIMIT OFFSET
    if offset and offset > 0:
        return f"LIMIT {limit} OFFSET {offset}"
    return f"LIMIT {limit}"


def normalize_sql_params(sql: str, params: list, db_type: str) -> tuple[str, list]:
    """
    规范化 SQL 参数占位符。

    Args:
        sql: SQL 模板
        params: 参数列表
        db_type: 数据库类型

    Returns:
        (规范化后的 SQL, 参数列表)
    """
    # 当前实现：保持 ? 占位符不变
    # 后续可扩展支持 :name, $1 等其他方言
    return (sql, params)


def preprocess_where_terms(where: list[dict], cls: Any, term_resolver) -> list[dict]:
    """
    预处理 WHERE 条件中的术语。

    将术语（如 "今年" 等）展开为具体值。

    Args:
        where: WHERE 条件列表
        cls: OntologyClass 对象
        term_resolver: 术语解析器

    Returns:
        处理后的 WHERE 条件列表
    """
    # 当前实现：直接返回原条件
    # 后续可集成 term_resolver 进行术语展开
    return where


def build_aggregate_sql(
    oql_params: dict,
    cls: Any,
    db_type: str,
    registry
) -> tuple[str, list]:
    """
    构建聚合查询 SQL。

    Args:
        oql_params: OQL 参数
        cls: OntologyClass 对象
        db_type: 数据库类型
        registry: 本体注册表

    Returns:
        (SQL 模板, 参数列表)
    """
    quoting = get_quoting(db_type)
    table = resolve_table(cls)
    alias = "t"
    params = []

    # 构建 SELECT 子句
    select_parts = []

    # GROUP BY 字段
    group_by_fields = oql_params.get("group_by", [])
    for gb in group_by_fields:
        field_code = gb.get("field")
        col_name = resolve_column(field_code, cls, db_type)
        select_parts.append(f"{alias}.{quoting}{col_name}{quoting} AS {quoting}{field_code}{quoting}")

    # 聚合指标
    metrics = oql_params.get("metrics", [])
    for metric in metrics:
        field_code = metric.get("field")
        agg_func = metric.get("aggregation", "sum").upper()
        col_name = resolve_column(field_code, cls, db_type)
        select_parts.append(f"{agg_func}({alias}.{quoting}{col_name}{quoting}) AS {quoting}{field_code}_{agg_func.lower()}{quoting}")

    # 构建 WHERE 子句
    where = oql_params.get("where", [])
    field_map = build_field_map(cls, [gb["field"] for gb in group_by_fields] + [m["field"] for m in metrics], db_type)
    where_clause = ""
    if where:
        where_clause = f"WHERE {translate_conditions(where, field_map, db_type, params, quoting)}"

    # 构建 GROUP BY 子句
    group_by_clause = ""
    if group_by_fields:
        gb_parts = [f"{alias}.{quoting}{resolve_column(gb['field'], cls, db_type)}{quoting}" for gb in group_by_fields]
        group_by_clause = f"GROUP BY {', '.join(gb_parts)}"

    # 构建 HAVING 子句
    having_clause = ""
    having = oql_params.get("having", [])
    if having:
        having_clause = f"HAVING {translate_conditions(having, {}, db_type, params, quoting, is_having=True)}"

    # 组装 SQL
    clauses = [
        f"SELECT {', '.join(select_parts)}",
        f"FROM {table} AS {alias}",
        where_clause,
        group_by_clause,
        having_clause,
        build_limit_clause(oql_params.get("limit", 100), oql_params.get("offset"), db_type),
    ]

    sql = "\n".join(c for c in clauses if c)
    return (sql, params)


# ============================================================================
# 策略 A：单源执行器
# ============================================================================

class OqlAdapter:
    """OQL 单源执行适配器"""

    def translate(
        self,
        oql_params: dict,
        registry,
        term_resolver,
        db_type: str
    ) -> SqlExecTask | ApiExecTask:
        """
        翻译 OQL 参数为执行任务。

        Args:
            oql_params: OQL 参数字典
            registry: 本体注册表
            term_resolver: 术语解析器
            db_type: 数据库类型

        Returns:
            SqlExecTask 或 ApiExecTask
        """
        cls = resolve_object(oql_params["object"], registry)

        if cls.source_type == "API":
            return self.translate_api(oql_params, cls)
        else:
            return self.translate_db(oql_params, cls, db_type, registry, term_resolver)

    def translate_db(
        self,
        oql_params: dict,
        cls: Any,
        db_type: str,
        registry,
        term_resolver
    ) -> SqlExecTask:
        """翻译 DB 对象查询为 SqlExecTask。"""
        where = preprocess_where_terms(oql_params.get("where", []), cls, term_resolver)

        # 收集所有涉及的字段
        all_fields = list({
            *oql_params.get("fields", []),
            *[c["field"] for c in where if "logic" not in c],
            *[gb["field"] for gb in oql_params.get("group_by", [])],
            *[ob["field"] for ob in oql_params.get("order_by", [])],
        })

        field_map = build_field_map(cls, all_fields, db_type)

        if oql_params.get("metrics"):
            sql, params = build_aggregate_sql(oql_params, cls, db_type, registry)
        else:
            sql, params = self._build_list_sql(oql_params, cls, db_type, registry, field_map, where)

        sql, params = normalize_sql_params(sql, params, db_type)

        return SqlExecTask(
            datasource_alias=cls.datasource_alias,
            sql_template=sql
        )

    def _build_list_sql(
        self,
        oql_params: dict,
        cls: Any,
        db_type: str,
        registry,
        field_map: dict[str, str],
        where: list[dict]
    ) -> tuple[str, list]:
        """构建列表查询 SQL。"""
        quoting = get_quoting(db_type)
        table = resolve_table(cls)
        alias = "t"
        params = []

        # SELECT 子句
        select_fields = oql_params.get("fields") or list(field_map.keys())
        select_cols = [
            f"{alias}.{quoting}{field_map[f]}{quoting} AS {quoting}{f}{quoting}"
            for f in select_fields
        ]

        # FROM 子句
        from_clause = f"FROM {table} AS {alias}"

        # WHERE 子句
        where_clause = ""
        if where:
            where_clause = f"WHERE {translate_conditions(where, field_map, db_type, params, quoting)}"

        # ORDER BY 子句
        ob_parts = []
        for ob in oql_params.get("order_by", []):
            field_code = ob["field"]
            direction = ob.get("direction", "asc").upper()
            col_name = field_map.get(field_code, field_code)
            ob_parts.append(f"{quoting}{col_name}{quoting} {direction}")

        order_by_clause = ""
        if ob_parts:
            order_by_clause = f"ORDER BY {', '.join(ob_parts)}"

        # LIMIT 子句
        limit_clause = build_limit_clause(
            oql_params.get("limit", 100),
            oql_params.get("offset", 0),
            db_type
        )

        # 组装 SQL
        clauses = [
            f"SELECT {', '.join(select_cols)}",
            from_clause,
            where_clause,
            order_by_clause,
            limit_clause,
        ]

        sql = "\n".join(c for c in clauses if c)
        return (sql, params)

    def translate_api(
        self,
        oql_params: dict,
        cls: Any
    ) -> ApiExecTask:
        """翻译 API 对象查询为 ApiExecTask。"""
        # 选择查询 action
        action = self._select_query_action(cls)

        # 构建参数
        params = {}

        # WHERE 条件：仅支持 eq/in
        unsupported_ops = set()
        for cond in oql_params.get("where", []):
            if "logic" in cond:
                continue
            if cond["op"] in ("eq", "in"):
                params[cond["field"]] = cond["value"]
            else:
                unsupported_ops.add(cond["op"])

        if unsupported_ops:
            logger.warning(
                "OQL translate_api: 对象 %s 的 WHERE 条件含不支持的操作符 %s，已跳过。"
                "API 对象 WHERE 仅支持 eq/in。",
                cls.object_code, unsupported_ops,
            )

        return ApiExecTask(
            object_code=cls.object_code,
            action_code=action.action_code,
            params=params
        )

    def _select_query_action(self, cls: Any) -> Any:
        """选择查询 action（当前简化实现）。"""
        # 简化实现：返回第一个 action
        if hasattr(cls, 'actions') and cls.actions:
            return cls.actions[0]
        raise OQLError(
            OQLErrorCode.OQL_ERR_UNSUPPORTED_OPERATION,
            f"对象 '{cls.object_code}' 没有可用的 action"
        )
