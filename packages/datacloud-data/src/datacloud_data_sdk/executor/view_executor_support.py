"""视图虚拟动作执行公共支持。"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import Any

from datacloud_data_sdk.sql_executor.data_source_manager import DataSourceManager


@dataclass(frozen=True)
class ViewExecutionContext:
    """视图执行所需的公共上下文。"""

    datasource_alias: str
    db_type: str
    anchor_table: str
    field_to_alias_col: dict[str, tuple[str, str]]
    field_to_object_code: dict[str, str]


def quote_identifier(ident: str, db_type: str) -> str:
    """按数据库类型引用标识符。"""
    dt = db_type.upper()
    if dt in ("POSTGRESQL", "OPENGAUSS", "SQLITE"):
        return f'"{ident}"'
    if dt in ("MYSQL", "CLICKHOUSE"):
        return f"`{ident}`"
    return ident


def join_key_fields(join_key: dict[str, Any]) -> tuple[str, str]:
    """统一读取关系 join key 的左右字段名。"""
    left = (
        join_key.get("source_field")
        or join_key.get("sourceField")
        or join_key.get("from_field")
        or join_key.get("from")
        or ""
    )
    right = (
        join_key.get("target_field")
        or join_key.get("targetField")
        or join_key.get("to_field")
        or join_key.get("to")
        or ""
    )
    return left, right


def build_view_execution_context(
    view: Any,
    ds_manager: DataSourceManager,
) -> ViewExecutionContext:
    """构建视图执行的通用上下文。"""
    if not getattr(view, "objects", None):
        return ViewExecutionContext("", "SQLITE", "", {}, {})

    anchor_cls = view.objects[0]._cls
    datasource_alias = anchor_cls.datasource_alias or ""
    config = ds_manager._configs.get(datasource_alias) if datasource_alias else None
    db_type = getattr(config, "db_type", "SQLITE") if config else "SQLITE"

    for obj in view.objects[1:]:
        obj_alias = obj._cls.datasource_alias or ""
        if obj_alias != datasource_alias:
            raise ValueError(
                f"View {view.view_id!r} contains multiple datasource aliases: "
                f"{datasource_alias!r} and {obj_alias!r}"
            )

    anchor_table = anchor_cls.table_name or anchor_cls.object_code
    field_to_alias_col: dict[str, tuple[str, str]] = {}
    field_to_object_code: dict[str, str] = {}
    all_view_fields = getattr(view, "fields", [])
    if all_view_fields:
        for vf in all_view_fields:
            field_code = getattr(vf, "property_code", None)
            if not field_code:
                continue
            source_object_code = getattr(vf, "source_object_code", "")
            source_column_code = getattr(vf, "source_object_column_code", field_code)
            for idx, obj in enumerate(view.objects):
                if obj.object_code == source_object_code:
                    source_column = _resolve_source_column(obj._cls, source_column_code)
                    field_to_alias_col[field_code] = (f"t{idx}", source_column)
                    field_to_object_code[field_code] = obj.object_code
                    break
    else:
        for idx, obj in enumerate(view.objects):
            for field in obj._cls.fields:
                if field.field_code in field_to_alias_col:
                    continue
                field_to_alias_col[field.field_code] = (
                    f"t{idx}",
                    field.source_column or field.field_code,
                )
                field_to_object_code[field.field_code] = obj.object_code

    return ViewExecutionContext(
        datasource_alias=datasource_alias,
        db_type=db_type,
        anchor_table=anchor_table,
        field_to_alias_col=field_to_alias_col,
        field_to_object_code=field_to_object_code,
    )


def _resolve_source_column(cls: Any, field_code: str) -> str:
    """按 field_code/source_column 查找真实物理列名。"""
    for field in getattr(cls, "fields", []) or []:
        if field.field_code == field_code or getattr(field, "source_column", None) == field_code:
            return getattr(field, "source_column", None) or field.field_code
    return field_code


def build_filters_where(
    filters: list[dict[str, Any]],
    field_to_alias_col: dict[str, tuple[str, str]],
    db_type: str,
    param_key_builder: Any,
    filter_relation: str = "AND",
) -> tuple[str, dict[str, Any]]:
    """构建支持表别名的 WHERE 子句。"""
    if not filters:
        return "", {}

    clauses: list[str] = []
    params: dict[str, Any] = {}

    for idx, item in enumerate(filters):
        field_code = item.get("field", "")
        op = item.get("op", "eq")
        value = item.get("value")
        resolved = field_to_alias_col.get(field_code)
        if not resolved:
            continue
        alias, col = resolved
        col_expr = f"{alias}.{quote_identifier(col, db_type)}"
        param_key = param_key_builder("p", field_code, idx)

        if op == "is_null":
            clauses.append(f"{col_expr} IS NULL")
        elif op == "is_not_null":
            clauses.append(f"{col_expr} IS NOT NULL")
        elif op == "between":
            values = value if isinstance(value, list) else [value, value]
            clauses.append(f"{col_expr} BETWEEN :{param_key}_0 AND :{param_key}_1")
            params[f"{param_key}_0"] = values[0]
            params[f"{param_key}_1"] = values[1]
        elif op == "in":
            values = value if isinstance(value, list) else [value]
            param_keys = [f"{param_key}_{i}" for i in range(len(values))]
            clauses.append(f"{col_expr} IN ({', '.join(f':{key}' for key in param_keys)})")
            for key, item_value in zip(param_keys, values, strict=False):
                params[key] = item_value
        elif op == "like":
            like_value = value if (isinstance(value, str) and "%" in value) else f"%{value}%"
            clauses.append(f"{col_expr} LIKE :{param_key}")
            params[param_key] = like_value
        else:
            op_map = {"eq": "=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
            clauses.append(f"{col_expr} {op_map.get(op, '=')} :{param_key}")
            params[param_key] = value

    relation = filter_relation.upper()
    return f" {relation} ".join(clauses), params


def collect_required_objects(
    view: Any,
    field_to_object_code: dict[str, str],
    referenced_fields: set[str],
) -> set[str]:
    """根据当前 SQL 引用的字段收集必需对象。"""
    if not getattr(view, "objects", None):
        return set()

    required_objects = {view.objects[0].object_code}
    for field_code in referenced_fields:
        object_code = field_to_object_code.get(field_code)
        if object_code:
            required_objects.add(object_code)
    return required_objects


def build_join_clauses(
    view: Any,
    db_type: str,
    required_objects: set[str] | None = None,
) -> list[str]:
    """构建只覆盖所需对象的 LEFT JOIN 子句列表。"""
    if not getattr(view, "objects", None):
        return []

    obj_alias = {obj.object_code: f"t{idx}" for idx, obj in enumerate(view.objects)}
    obj_table = {
        obj.object_code: getattr(obj._cls, "table_name", obj.object_code) for obj in view.objects
    }
    valid_objects = set(obj_alias)
    anchor_object = view.objects[0].object_code
    target_objects = set(required_objects or valid_objects) & valid_objects
    target_objects.add(anchor_object)
    closure_objects = _resolve_join_closure(view, anchor_object, target_objects)

    clauses: list[str] = []
    joined_objects = {anchor_object}
    pending_relations = list(view.relations)

    while pending_relations:
        progressed = False
        remaining_relations: list[Any] = []
        for rel in pending_relations:
            src = getattr(rel, "from_object", None) or getattr(rel, "source_class", "")
            tgt = getattr(rel, "to_object", None) or getattr(rel, "target_class", "")
            join_keys = getattr(rel, "join_keys", [])
            if not src or not tgt or not join_keys:
                continue
            if src not in closure_objects or tgt not in closure_objects:
                continue

            src_joined = src in joined_objects
            tgt_joined = tgt in joined_objects
            if src_joined and tgt_joined:
                continue
            if not src_joined and not tgt_joined:
                remaining_relations.append(rel)
                continue

            if src_joined:
                base_alias = obj_alias.get(src, "t0")
                join_obj, join_alias = tgt, obj_alias.get(tgt, "t1")
                left_index = 0
                right_index = 1
            else:
                base_alias = obj_alias.get(tgt, "t0")
                join_obj, join_alias = src, obj_alias.get(src, "t1")
                left_index = 1
                right_index = 0

            join_table = obj_table.get(join_obj, join_obj)
            on_parts: list[str] = []
            for join_key in join_keys:
                fields = join_key_fields(join_key)
                left_field = fields[left_index]
                right_field = fields[right_index]
                if left_field and right_field:
                    on_parts.append(
                        f"{base_alias}.{quote_identifier(left_field, db_type)} = "
                        f"{join_alias}.{quote_identifier(right_field, db_type)}"
                    )
            if on_parts:
                clauses.append(
                    f"LEFT JOIN {quote_identifier(join_table, db_type)} {join_alias} "
                    f"ON {' AND '.join(on_parts)}"
                )
                joined_objects.add(join_obj)
                progressed = True

        if not progressed:
            break
        pending_relations = remaining_relations

    missing_objects = closure_objects - joined_objects
    if missing_objects:
        raise ValueError(
            f"View {view.view_id!r} missing join path for objects: {sorted(missing_objects)}"
        )
    return clauses


def _resolve_join_closure(
    view: Any,
    anchor_object: str,
    target_objects: set[str],
) -> set[str]:
    """为目标对象计算最小可连接对象闭包。"""
    adjacency: dict[str, list[str]] = {}
    for rel in getattr(view, "relations", []):
        src = getattr(rel, "from_object", None) or getattr(rel, "source_class", "")
        tgt = getattr(rel, "to_object", None) or getattr(rel, "target_class", "")
        join_keys = getattr(rel, "join_keys", [])
        if not src or not tgt or not join_keys:
            continue
        adjacency.setdefault(src, []).append(tgt)
        adjacency.setdefault(tgt, []).append(src)

    parents: dict[str, str | None] = {anchor_object: None}
    queue: list[str] = [anchor_object]
    while queue:
        current = queue.pop(0)
        for neighbor in adjacency.get(current, []):
            if neighbor in parents:
                continue
            parents[neighbor] = current
            queue.append(neighbor)

    closure_objects = {anchor_object}
    for target in target_objects:
        if target == anchor_object:
            continue
        if target not in parents:
            raise ValueError(
                f"View {view.view_id!r} has no join path from {anchor_object!r} to {target!r}"
            )
        current: str | None = target
        while current is not None:
            closure_objects.add(current)
            current = parents[current]
    return closure_objects


def build_view_result_columns_meta(
    view: Any,
    col_keys: list[str],
    loader: Any = None,
) -> list[dict[str, str]]:
    """将视图查询结果列键规范为与 ``QueryExecutor`` 一致的 ``meta.columns`` 结构。

    原先仅返回 ``property_code`` 字符串列表，前端 / Markdown 无法取中文 ``label``。
    此处按视图 ``fields``（``ViewFieldMeta``）映射 ``name``=行内键、``label``=展示名。
    当 OWL 未定义 ``property_name`` 时，通过 ``loader`` 从源对象字段派生中文名。

    Args:
        view: 已加载的视图对象（含 ``fields``）。
        col_keys: SELECT 结果列顺序，与 ``records`` 行字典的 key 一致。
        loader: 本体加载器（可选），用于在 ``property_name`` 缺失时派生中文 label。

    Returns:
        ``[{"name": code, "label": display, "type": "..."}, ...]``；未知列 ``label`` 回退为 ``name``。
    """
    if not col_keys:
        return []

    code_to_field: dict[str, Any] = {}
    for vf in getattr(view, "fields", []) or []:
        code = str(getattr(vf, "property_code", "") or "").strip()
        if code:
            code_to_field[code] = vf

    out: list[dict[str, str]] = []
    for fc in col_keys:
        vf = code_to_field.get(fc)
        label = str(getattr(vf, "property_name", "") or "").strip() if vf else ""
        if not label:
            label = fc
        # property_name 退化为字段编码（OWL 未定义中文名）时，从源对象字段派生
        if label == fc and loader is not None and vf is not None:
            label = _derive_label_from_source(vf, fc, loader)
        raw_type = getattr(vf, "field_type", None) if vf else None
        ft = str(raw_type or "string").lower()
        out.append({"name": fc, "label": label, "type": ft})
    return out


def _derive_label_from_source(vf: Any, fc: str, loader: Any) -> str:
    """从源对象字段派生中文 label（OWL property_name 缺失时的兜底）。"""
    src_obj_code = str(getattr(vf, "source_object_code", "") or "").strip()
    src_col_code = str(getattr(vf, "source_object_column_code", "") or "").strip()
    if not src_obj_code or not src_col_code:
        return fc
    with contextlib.suppress(Exception):
        src_cls = loader.get_ontology_class(src_obj_code)
        for f in getattr(src_cls, "fields", []):
            if getattr(f, "field_code", None) == src_col_code:
                fname = str(getattr(f, "field_name", "") or "").strip()
                if fname and fname != src_col_code:
                    return fname
                break
    return fc
