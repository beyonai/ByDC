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

def route_by_source_type(cls: Any) -> str:
    """
    根据对象类型路由到对应的执行策略。

    Args:
        cls: OntologyClass 对象

    Returns:
        执行策略类型：'sql' 或 'api'

    Raises:
        OQLError: 不支持的对象类型
    """
    if cls.source_type == "DB":
        return "sql"
    elif cls.source_type == "API":
        return "api"
    else:
        raise OQLError(
            OQLErrorCode.OQL_ERR_UNSUPPORTED_OPERATION,
            f"对象 '{cls.object_code}' 的类型 '{cls.source_type}' 不支持 QueryObjects"
        )


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


def find_primary_key(cls: Any, db_type: str) -> tuple[str, str]:
    """
    查找对象的主键。

    返回 (field_code, physical_column)，优先取 is_primary_key=True 的字段。

    Args:
        cls: OntologyClass 对象
        db_type: 数据库类型

    Returns:
        (字段代码, 物理列名) 元组

    Raises:
        OQLError: 对象未定义任何字段
    """
    # 优先查找标记为主键的字段
    if hasattr(cls, 'fields'):
        for f in cls.fields:
            if hasattr(f, 'is_primary_key') and f.is_primary_key:
                return f.field_code, resolve_column(f.field_code, cls, db_type)

        # 如果没有标记的主键，使用第一个字段
        if cls.fields:
            f = cls.fields[0]
            return f.field_code, resolve_column(f.field_code, cls, db_type)

    raise OQLError(
        OQLErrorCode.OQL_ERR_UNKNOWN_FIELD,
        f"对象 '{cls.object_code}' 未定义任何字段"
    )



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


def resolve_term_value(field: Any, raw_value: Any, term_resolver) -> Any:
    """
    将业务名称转换为物理值。

    对于含 term_set 的字段，通过 term_resolver 将标签/别名解析为标准值。
    无 term_set 时直接返回原始值。

    Args:
        field: OntologyField 对象
        raw_value: 原始值（可能是标签/别名）
        term_resolver: 术语解析器（TermResolver 实例）

    Returns:
        解析后的物理值

    Raises:
        OQLError: 术语解析失败
    """
    if not field.term_set:
        return raw_value

    if term_resolver is None:
        logger.warning(
            "字段 '%s' 配置了 term_set '%s' 但未提供 term_resolver，跳过术语解析",
            field.field_code, field.term_set
        )
        return raw_value

    try:
        # 获取 term_loader
        term_loader = getattr(term_resolver, 'term_loader', None) or getattr(term_resolver, '_term_loader', None)
        if term_loader is None:
            logger.warning(
                "term_resolver 未配置 term_loader，字段 '%s' 跳过术语解析",
                field.field_code
            )
            return raw_value

        # 列表值：逐个解析
        if isinstance(raw_value, list):
            return [
                term_loader.resolve_value(
                    field.term_set,
                    str(v),
                    term_field=field.term_field,
                    dataset_id=field.dataset_id,
                    term_type_code=field.term_set.split(".")[0] if "." in (field.term_set or "") else None,
                    param_name=field.field_name or field.field_code,
                )
                for v in raw_value
            ]

        # 单值解析
        return term_loader.resolve_value(
            field.term_set,
            str(raw_value),
            term_field=field.term_field,
            dataset_id=field.dataset_id,
            term_type_code=field.term_set.split(".")[0] if "." in (field.term_set or "") else None,
            param_name=field.field_name or field.field_code,
        )

    except Exception as e:
        # 术语解析失败时抛出 OQLError
        raise OQLError(
            OQLErrorCode.OQL_ERR_TERM_RESOLUTION_FAILED,
            f"字段 '{field.field_code}' 术语解析失败: {e}"
        )


def preprocess_where_terms(where: list[dict], cls: Any, term_resolver) -> list[dict]:
    """
    预处理 WHERE 条件中的术语。

    对于含 term_set 的字段，将条件值中的标签/别名解析为物理存储值。
    在条件翻译之前调用。

    Args:
        where: WHERE 条件列表
        cls: OntologyClass 对象
        term_resolver: 术语解析器（TermResolver 实例）

    Returns:
        处理后的 WHERE 条件列表

    Raises:
        OQLError: 术语解析失败
    """
    if not where:
        return where

    # 构建字段索引
    field_index = {f.field_code: f for f in cls.fields}
    result = []

    for cond in where:
        # 逻辑操作符（AND/OR）直接保留
        if "logic" in cond:
            result.append(cond)
            continue

        # 获取字段定义
        field_code = cond.get("field")
        if not field_code:
            result.append(cond)
            continue

        field_obj = field_index.get(field_code)
        if not field_obj:
            # 字段不存在，保留原条件（后续翻译时会报错）
            result.append(cond)
            continue

        # 无 term_set 或无 value 的条件直接保留
        if not field_obj.term_set or "value" not in cond:
            result.append(cond)
            continue

        # 对于 is_null/is_not_null 操作符，不需要解析 value
        op = cond.get("op", "")
        if op in ("is_null", "is_not_null"):
            result.append(cond)
            continue

        # 解析术语值
        try:
            resolved_value = resolve_term_value(field_obj, cond["value"], term_resolver)
            result.append({**cond, "value": resolved_value})
        except OQLError:
            # 术语解析失败，直接向上抛出
            raise
        except Exception as e:
            # 其他异常，包装为 OQLError
            raise OQLError(
                OQLErrorCode.OQL_ERR_TERM_RESOLUTION_FAILED,
                f"字段 '{field_code}' 术语解析时发生异常: {e}"
            )

    return result


def resolve_include_links(include_links: list[dict], root_cls: Any, root_alias: str, registry, db_type: str) -> tuple[str, list[str]]:
    """
    将同源 include_links 翻译为 LEFT JOIN 片段和附加 SELECT 列。

    返回 (join_sql, extra_select_cols)
    列别名格式 "{path__field}"，与策略 B 内存合并的结果列名保持一致。

    Args:
        include_links: include_links 列表
        root_cls: 根对象
        root_alias: 根表别名
        registry: 本体注册表
        db_type: 数据库类型

    Returns:
        (JOIN SQL 片段, 附加 SELECT 列列表) 元组

    Raises:
        OQLError: 关系不存在或路径过深
    """
    join_parts = []
    select_cols = []
    generated_paths = {"": root_alias}
    quoting = get_quoting(db_type)

    for clause in include_links:
        path = clause.get("path", "")
        select_fields = clause.get("select", [])
        path_segments = path.split(".")

        if len(path_segments) > 5:
            raise OQLError(
                OQLErrorCode.OQL_ERR_INVALID_OPERATOR,
                f"关系路径过深：{path}（最多 5 层）"
            )

        current_prefix = ""
        current_alias = root_alias
        current_cls = root_cls

        for segment in path_segments:
            parent_prefix = current_prefix
            current_prefix = f"{parent_prefix}.{segment}" if parent_prefix else segment

            # 查找关系
            rel = None
            if hasattr(current_cls, 'relations'):
                for r in current_cls.relations:
                    if r.relation_code == segment:
                        rel = r
                        break

            if rel is None:
                raise OQLError(
                    OQLErrorCode.OQL_ERR_UNKNOWN_RELATION,
                    f"关系 '{segment}' 不存在于对象 '{current_cls.object_code}'"
                )

            target_cls = registry.get_class(rel.target_class)
            if target_cls is None:
                raise OQLError(
                    OQLErrorCode.OQL_ERR_UNKNOWN_OBJECT,
                    f"目标对象 '{rel.target_class}' 不存在"
                )

            # 如果路径已生成，跳过 JOIN
            if current_prefix in generated_paths:
                current_alias = generated_paths[current_prefix]
                current_cls = target_cls
                continue

            # 生成新的 JOIN 别名
            join_alias = f"_j{len(generated_paths)}"
            generated_paths[current_prefix] = join_alias

            # 构建 ON 条件
            on_parts = []
            join_keys = rel.join_keys if hasattr(rel, 'join_keys') else {}
            for src_field, tgt_field in join_keys.items():
                src_col = resolve_column(src_field, current_cls, db_type)
                tgt_col = resolve_column(tgt_field, target_cls, db_type)
                on_parts.append(
                    f"{generated_paths[parent_prefix]}.{quoting}{src_col}{quoting} = {join_alias}.{quoting}{tgt_col}{quoting}"
                )

            join_parts.append(
                f"LEFT JOIN {resolve_table(target_cls)} AS {join_alias} ON {' AND '.join(on_parts)}"
            )

            current_alias = join_alias
            current_cls = target_cls

        # 构建 SELECT 列
        col_prefix = path.replace(".", "__")
        fields_to_sel = select_fields or [f.field_code for f in current_cls.fields]
        for field_name in fields_to_sel:
            # 查找字段
            field_obj = None
            for f in current_cls.fields:
                if f.field_code == field_name:
                    field_obj = f
                    break

            if field_obj is None:
                raise OQLError(
                    OQLErrorCode.OQL_ERR_UNKNOWN_FIELD,
                    f"字段 '{field_name}' 不存在于对象 '{current_cls.object_code}'"
                )

            col_name = resolve_column(field_name, current_cls, db_type)
            select_cols.append(
                f'{current_alias}.{quoting}{col_name}{quoting} AS {quoting}{col_prefix}__{field_name}{quoting}'
            )

    return "\n".join(join_parts), select_cols



def build_metric_expr(alias: str, metric: dict, cls: Any, db_type: str, quoting: str = '"') -> str:
    """
    构建聚合指标表达式。

    Args:
        alias: 表别名
        metric: 指标定义 {name, op, field?}
        cls: OntologyClass 对象
        db_type: 数据库类型
        quoting: SQL 引号字符

    Returns:
        聚合表达式字符串

    Raises:
        OQLError: 不支持的聚合操作符
    """
    name = metric.get("name", "metric")
    op = metric.get("op", "sum").lower()
    field = metric.get("field")

    name_q = f"{quoting}{name}{quoting}"

    if op == "count":
        return f"COUNT(*) AS {name_q}"

    if not field:
        raise OQLError(
            OQLErrorCode.OQL_ERR_INVALID_OPERATOR,
            f"聚合操作 '{op}' 需要指定字段"
        )

    col_name = resolve_column(field, cls, db_type)
    col_expr = f"{alias}.{quoting}{col_name}{quoting}"

    mapping = {
        "count_distinct": f"COUNT(DISTINCT {col_expr})",
        "sum": f"SUM({col_expr})",
        "avg": f"AVG({col_expr})",
        "max": f"MAX({col_expr})",
        "min": f"MIN({col_expr})",
    }

    if op not in mapping:
        raise OQLError(
            OQLErrorCode.OQL_ERR_INVALID_OPERATOR,
            f"不支持的聚合操作符：{op}"
        )

    return f"{mapping[op]} AS {name_q}"


def time_trunc_expr(col_expr: str, granularity: str, db_type: str) -> str:
    """
    构建时间截断表达式。

    Args:
        col_expr: 列表达式（如 "t.created_at"）
        granularity: 粒度（day/week/month/quarter/year）
        db_type: 数据库类型

    Returns:
        时间截断表达式

    Raises:
        OQLError: 不支持的粒度或数据库类型
    """
    db_type_upper = db_type.upper()
    granularity_lower = granularity.lower()

    # MySQL / MariaDB
    if db_type_upper in ("MYSQL", "MARIADB"):
        mapping = {
            "day": f"DATE({col_expr})",
            "week": f"DATE_FORMAT({col_expr},'%Y-%u')",
            "month": f"DATE_FORMAT({col_expr},'%Y-%m')",
            "quarter": f"CONCAT(YEAR({col_expr}),'-Q',QUARTER({col_expr}))",
            "year": f"YEAR({col_expr})",
        }
    # PostgreSQL / OpenGauss
    elif db_type_upper in ("POSTGRESQL", "OPENGAUSS"):
        mapping = {
            "day": f"DATE_TRUNC('day',{col_expr})",
            "week": f"DATE_TRUNC('week',{col_expr})",
            "month": f"DATE_TRUNC('month',{col_expr})",
            "quarter": f"DATE_TRUNC('quarter',{col_expr})",
            "year": f"DATE_TRUNC('year',{col_expr})",
        }
    # Hive
    elif db_type_upper == "HIVE":
        mapping = {
            "day": f"TO_DATE({col_expr})",
            "week": f"DATE_FORMAT({col_expr},'yyyy-ww')",
            "month": f"DATE_FORMAT({col_expr},'yyyy-MM')",
            "quarter": f"CONCAT(YEAR({col_expr}),'-Q',CEIL(MONTH({col_expr})/3.0))",
            "year": f"YEAR({col_expr})",
        }
    # ClickHouse
    elif db_type_upper == "CLICKHOUSE":
        mapping = {
            "day": f"toDate({col_expr})",
            "week": f"toStartOfWeek({col_expr})",
            "month": f"toStartOfMonth({col_expr})",
            "quarter": f"toStartOfQuarter({col_expr})",
            "year": f"toStartOfYear({col_expr})",
        }
    # SQLite
    elif db_type_upper == "SQLITE":
        mapping = {
            "day": f"DATE({col_expr})",
            "week": f"strftime('%Y-%W',{col_expr})",
            "month": f"strftime('%Y-%m',{col_expr})",
            "quarter": f"strftime('%Y',{col_expr})||'-Q'||((CAST(strftime('%m',{col_expr}) AS INT)+2)/3)",
            "year": f"strftime('%Y',{col_expr})",
        }
    else:
        # 默认使用 MySQL 方言
        mapping = {
            "day": f"DATE({col_expr})",
            "week": f"DATE_FORMAT({col_expr},'%Y-%u')",
            "month": f"DATE_FORMAT({col_expr},'%Y-%m')",
            "quarter": f"CONCAT(YEAR({col_expr}),'-Q',QUARTER({col_expr}))",
            "year": f"YEAR({col_expr})",
        }

    if granularity_lower not in mapping:
        raise OQLError(
            OQLErrorCode.OQL_ERR_INVALID_OPERATOR,
            f"不支持的时间粒度：{granularity}"
        )

    return mapping[granularity_lower]


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
