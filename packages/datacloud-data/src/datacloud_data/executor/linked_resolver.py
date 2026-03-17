"""LinkedResolver: API + DB 跨源 linked 字段批量解析。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datacloud_data.ontology.loader import OntologyLoader
    from datacloud_data.ontology.models import OntologyField, OntologyRelation
    from datacloud_data.sql_executor.data_source_manager import DataSourceManager


def _action_supports_batch(loader: OntologyLoader, source_class: str, action_code: str) -> bool:
    """检查 action 的 input_schema 是否有 array 类型 IN 参数（支持批量）。"""
    cls = loader.get_ontology_class(source_class)
    action = next((a for a in cls.actions if a.action_code == action_code), None)
    if not action:
        return False
    if action.input_schema:
        props = action.input_schema.get("properties", {})
        for p in (action.params or []):
            if p.direction not in ("IN", "INOUT"):
                continue
            schema_type = props.get(p.param_code, {}).get("type") if isinstance(props.get(p.param_code), dict) else None
            if schema_type == "array":
                return True
            if (p.param_type or "").upper() in ("ARRAY", "LIST"):
                return True
    for p in (action.params or []):
        if p.direction in ("IN", "INOUT") and (p.param_type or "").upper() in ("ARRAY", "LIST"):
            return True
    return False


async def resolve_api_linked_batch(
    loader: OntologyLoader,
    parents: list[dict[str, Any]],
    field: OntologyField,
    relation: OntologyRelation,
) -> list[list[dict[str, Any]]]:
    """解析 API linked 字段，返回与 parents 同序的 target 列表。

    支持批量：若 action 支持 array 入参则一次调用；否则逐条调用。
    """
    action_code = relation.resolve_action_code
    binding = relation.resolve_param_binding or {}
    source_field = binding.get("source_field")
    action_param = binding.get("action_param")
    if not action_code or not source_field or not action_param:
        return [[] for _ in parents]

    source_class = relation.source_class
    obj = loader.get_object(source_class)

    values = [p.get(source_field) for p in parents]

    if _action_supports_batch(loader, source_class, action_code):
        # 批量：一次调用传入数组
        params = {action_param: values}
        result = await obj.invoke_action(action_code, params)
        records = result.get("records", []) if isinstance(result, dict) else []
        # 按 source_field 分组：需从 records 中取 target 的 join_to 字段映射回 source
        # API 批量返回可能是 [{customer_id, ...}, ...] 或按 customer_id 分组的结构
        # 若返回是扁平的 list，需按 target 表中与 source 关联的字段分组
        target_class = relation.target_class
        join_keys = relation.join_keys or []
        join_to_field = join_keys[0].get("to_field") if join_keys else None
        if join_to_field:
            grouped: dict[Any, list[dict]] = {}
            for r in records:
                key = r.get(join_to_field)
                if key not in grouped:
                    grouped[key] = []
                grouped[key].append(r)
            return [grouped.get(v, []) for v in values]
        # 无 join_to 时，假设 API 返回顺序与 values 一致或返回单列表，均分
        if len(records) == len(parents):
            return [[r] for r in records]
        return [records for _ in parents] if records else [[] for _ in parents]

    # 逐条调用
    results: list[list[dict]] = []
    for v in values:
        params = {action_param: v}
        result = await obj.invoke_action(action_code, params)
        recs = result.get("records", []) if isinstance(result, dict) else []
        results.append(recs if isinstance(recs, list) else [])
    return results


async def resolve_db_linked_batch(
    loader: OntologyLoader,
    parents: list[dict[str, Any]],
    field: OntologyField,
    relation: OntologyRelation,
    ds_manager: DataSourceManager,
) -> list[list[dict[str, Any]]]:
    """解析 DB 跨源 linked 字段，一次 IN 查询，按 join_to 分组后映射回 parents。"""
    join_keys = relation.join_keys or []
    if not join_keys:
        return [[] for _ in parents]

    from_field = join_keys[0].get("from_field")
    to_field = join_keys[0].get("to_field")
    if not from_field or not to_field:
        return [[] for _ in parents]

    target_class = relation.target_class
    target_cls = loader.get_ontology_class(target_class)
    table_name = target_cls.table_name or target_class
    datasource_alias = target_cls.datasource_alias
    if not datasource_alias:
        return [[] for _ in parents]

    values = [p.get(from_field) for p in parents]
    unique_values = list(dict.fromkeys(v for v in values if v is not None))

    if not unique_values:
        return [[] for _ in parents]

    connector = ds_manager.get_connector(datasource_alias)
    field_to_col = {f.field_code: (f.source_column or f.field_code) for f in target_cls.fields}
    to_col = field_to_col.get(to_field, to_field)

    from datacloud_data.executor.db_sql_builder import build_where_clause

    db_type = "SQLITE"
    if target_cls.source_config and isinstance(target_cls.source_config, dict):
        db_type = target_cls.source_config.get("db_type", "SQLITE")

    where_sql, params = build_where_clause({to_field: {"op": "in", "value": unique_values}}, field_to_col)
    if not where_sql:
        return [[] for _ in parents]

    _dq = {"POSTGRESQL", "OPENGAUSS", "SQLITE"}
    _q = lambda x: f'"{x}"' if db_type.upper() in _dq else f"`{x}`"
    cols = [f.source_column or f.field_code for f in target_cls.fields]
    select_list = ", ".join(_q(c) for c in cols)
    sql = f'SELECT {select_list} FROM {_q(table_name)} WHERE {where_sql}'

    rows = await connector.execute(sql, params)

    # 按 join_to 分组
    grouped: dict[Any, list[dict]] = {v: [] for v in unique_values}
    for row in rows:
        key = row.get(to_col) or row.get(to_field)
        grouped.setdefault(key, []).append(dict(row))

    return [grouped.get(v, []) for v in values]
