"""视图跨数据源执行支持。"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from typing import Any

from datacloud_data_sdk.object import Object
from datacloud_data_sdk.relation import Relation
from datacloud_data_sdk.view import View


@dataclass(frozen=True)
class ViewRequestPlan:
    """视图请求的执行规划摘要。"""

    referenced_fields: set[str]
    closure_object_codes: tuple[str, ...]
    datasource_aliases: tuple[str, ...]
    anchor_object_code: str


@dataclass(frozen=True)
class ViewJoinEdge:
    """联邦预热用的 join 边信息。"""

    parent_object_code: str
    child_object_code: str
    parent_field_code: str
    child_field_code: str


def object_source_alias(obj: Any) -> str:
    """返回对象所属数据源别名。"""
    return str(getattr(obj._cls, "datasource_alias", "") or "")


def collect_view_field_object_map(view: Any) -> dict[str, str]:
    """构建视图字段到对象编码的映射。"""
    mapping: dict[str, str] = {}
    view_fields = list(getattr(view, "fields", []) or [])
    if view_fields:
        for field in view_fields:
            field_code = str(getattr(field, "property_code", "") or "").strip()
            object_code = str(getattr(field, "source_object_code", "") or "").strip()
            if field_code and object_code:
                mapping[field_code] = object_code
        if mapping:
            return mapping

    for obj in getattr(view, "objects", []) or []:
        for field in getattr(obj._cls, "fields", []):
            field_code = str(getattr(field, "field_code", "") or "").strip()
            if field_code and field_code not in mapping:
                mapping[field_code] = obj.object_code
    return mapping


def collect_referenced_fields(view: Any, arguments: dict[str, Any], mode: str) -> set[str]:
    """根据请求参数收集当前真正引用到的视图字段。"""
    field_to_object = collect_view_field_object_map(view)
    all_fields = set(field_to_object)
    referenced: set[str] = set()

    if mode == "query":
        select_codes = arguments.get("select") or []
        if select_codes:
            referenced.update(str(code) for code in select_codes if isinstance(code, str))
        else:
            referenced.update(all_fields)

        for item in arguments.get("filters") or []:
            field_code = item.get("field", "")
            if field_code:
                referenced.add(str(field_code))
        for item in arguments.get("order_by") or []:
            field_code = item.get("field", "")
            if field_code:
                referenced.add(str(field_code))
    else:
        dimensions = arguments.get("dimensions") or []
        metrics = arguments.get("metrics") or []
        filters = arguments.get("filters") or []
        order_by = arguments.get("order_by") or []

        for item in dimensions:
            if isinstance(item, dict):
                field_code = item.get("field", "")
                if field_code:
                    referenced.add(str(field_code))
        for item in metrics:
            if isinstance(item, dict) and item.get("agg") != "count_all":
                field_code = item.get("field", "")
                if field_code:
                    referenced.add(str(field_code))
        for item in filters:
            field_code = item.get("field", "")
            if field_code:
                referenced.add(str(field_code))
        metric_aliases = {
            str(item.get("as") or f"{item.get('agg', 'count')}_result")
            for item in metrics
            if isinstance(item, dict)
        }
        for item in order_by:
            field_code = item.get("field", "")
            if field_code and str(field_code) not in metric_aliases:
                referenced.add(str(field_code))

        if not referenced:
            referenced.update(all_fields)

    return {field_code for field_code in referenced if field_code in field_to_object}


def analyze_view_request(view: Any, arguments: dict[str, Any], mode: str) -> ViewRequestPlan:
    """分析视图请求命中的对象闭包和数据源集合。"""
    from datacloud_data_sdk.executor.view_executor_support import _resolve_join_closure

    field_to_object = collect_view_field_object_map(view)
    referenced_fields = collect_referenced_fields(view, arguments, mode)
    if not referenced_fields:
        referenced_fields = set(field_to_object)

    target_objects = {field_to_object[field_code] for field_code in referenced_fields}
    ordered_objects = [obj.object_code for obj in getattr(view, "objects", []) or []]
    anchor_object_code = next(
        (object_code for object_code in ordered_objects if object_code in target_objects),
        ordered_objects[0] if ordered_objects else "",
    )
    if not anchor_object_code:
        return ViewRequestPlan(set(), (), (), "")

    closure_objects = _resolve_join_closure(view, anchor_object_code, target_objects)
    ordered_closure = tuple(
        object_code for object_code in ordered_objects if object_code in closure_objects
    )

    object_to_source = {
        obj.object_code: object_source_alias(obj) for obj in getattr(view, "objects", []) or []
    }
    ordered_sources = tuple(
        dict.fromkeys(
            object_to_source[object_code] for object_code in ordered_closure if object_code
        )
    )
    return ViewRequestPlan(referenced_fields, ordered_closure, ordered_sources, anchor_object_code)


def collect_pushdown_filters(
    view: Any, arguments: dict[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    """收集可安全下推到对象源表的过滤条件。"""
    filters = list(arguments.get("filters") or [])
    if not filters:
        return {}

    field_to_object = collect_view_field_object_map(view)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    touched_objects: set[str] = set()

    for item in filters:
        field_code = str(item.get("field", "") or "")
        object_code = field_to_object.get(field_code)
        if not object_code:
            return {}
        grouped[object_code].append(dict(item))
        touched_objects.add(object_code)

    filter_relation = str(arguments.get("filter_relation") or "AND").upper()
    if filter_relation == "AND":
        return dict(grouped)
    return {}


def collect_filtered_field_codes(arguments: dict[str, Any]) -> set[str]:
    """收集请求中已显式过滤的字段编码。"""
    filtered_codes: set[str] = set()
    for item in arguments.get("filters") or []:
        field_code = str(item.get("field", "") or "")
        if field_code:
            filtered_codes.add(field_code)
    return filtered_codes


def build_join_edges(view: Any, plan: ViewRequestPlan) -> list[ViewJoinEdge]:
    """基于 anchor 对象构建 join 预热边。"""
    from datacloud_data_sdk.executor.view_executor_support import join_key_fields

    object_code_set = set(plan.closure_object_codes)
    adjacency: dict[str, list[ViewJoinEdge]] = defaultdict(list)
    for rel in getattr(view, "relations", []) or []:
        source_object = getattr(rel, "from_object", "") or getattr(rel, "source_class", "")
        target_object = getattr(rel, "to_object", "") or getattr(rel, "target_class", "")
        if source_object not in object_code_set or target_object not in object_code_set:
            continue
        for join_key in getattr(rel, "join_keys", []) or []:
            parent_field_code, child_field_code = (
                str(part or "") for part in join_key_fields(join_key)
            )
            if not parent_field_code or not child_field_code:
                continue
            adjacency[source_object].append(
                ViewJoinEdge(source_object, target_object, parent_field_code, child_field_code)
            )
            adjacency[target_object].append(
                ViewJoinEdge(target_object, source_object, child_field_code, parent_field_code)
            )

    if not plan.anchor_object_code:
        return []

    visited = {plan.anchor_object_code}
    queue = [plan.anchor_object_code]
    edges: list[ViewJoinEdge] = []
    while queue:
        current = queue.pop(0)
        for edge in adjacency.get(current, []):
            if edge.child_object_code in visited:
                continue
            visited.add(edge.child_object_code)
            queue.append(edge.child_object_code)
            edges.append(edge)
    return edges


def recommend_federated_filters(
    view: Any,
    plan: ViewRequestPlan,
    arguments: dict[str, Any],
    *,
    max_items: int = 3,
) -> list[dict[str, str]]:
    """为联邦行数保护生成过滤建议。"""
    filtered_codes = collect_filtered_field_codes(arguments)
    join_edges = build_join_edges(view, plan)
    join_field_pairs = {
        (edge.parent_object_code, edge.parent_field_code) for edge in join_edges
    } | {(edge.child_object_code, edge.child_field_code) for edge in join_edges}

    candidates: list[tuple[int, dict[str, str]]] = []
    for field in list(getattr(view, "fields", []) or []):
        field_code = str(getattr(field, "property_code", "") or "")
        object_code = str(getattr(field, "source_object_code", "") or "")
        source_column_code = str(getattr(field, "source_object_column_code", "") or field_code)
        if (
            not field_code
            or object_code not in plan.closure_object_codes
            or field_code in filtered_codes
        ):
            continue

        field_name = str(getattr(field, "property_name", "") or field_code)
        analytic_kind = str(getattr(field, "analytic_kind", "") or "")
        required_group = str(getattr(field, "required_filter_group", "") or "")

        score = 40
        reason = "高选择性过滤"
        if required_group:
            score = 100
            reason = "当前视图存在强制/高优先级过滤约束"
        elif analytic_kind in {"period", "datetime"}:
            score = 90
            reason = "时间或账期字段通常最能缩小联邦范围"
        elif object_code == plan.anchor_object_code and analytic_kind in {"id", "name"}:
            score = 80
            reason = "主对象标识字段能快速缩小候选集"
        elif (
            object_code == plan.anchor_object_code
            and (object_code, source_column_code) in join_field_pairs
        ):
            score = 70
            reason = "关联键字段能减少后续 join 预热范围"
        elif analytic_kind in {"id", "name"}:
            score = 60
            reason = "标识字段通常比普通维度过滤更有效"

        candidates.append(
            (
                score,
                {
                    "field": field_code,
                    "label": field_name,
                    "reason": reason,
                },
            )
        )

    candidates.sort(key=lambda item: (-item[0], item[1]["field"]))
    suggested: list[dict[str, str]] = []
    for _, candidate in candidates:
        if candidate in suggested:
            continue
        suggested.append(candidate)
        if len(suggested) >= max_items:
            break
    return suggested


def build_view_slice(
    view: Any,
    object_codes: tuple[str, ...],
    *,
    datasource_alias: str | None = None,
    local_table_names: bool = False,
) -> View:
    """按对象闭包构造视图切片，可选替换为本地临时表元数据。"""
    object_code_set = set(object_codes)
    ordered_objects = [
        obj for obj in getattr(view, "objects", []) or [] if obj.object_code in object_code_set
    ]
    ordered_relations = [
        rel
        for rel in getattr(view, "relations", []) or []
        if getattr(rel, "from_object", "") in object_code_set
        and getattr(rel, "to_object", "") in object_code_set
    ]
    view_fields = [
        field
        for field in list(getattr(view, "fields", []) or [])
        if getattr(field, "source_object_code", "") in object_code_set
    ]

    sliced_objects: list[Object] = []
    for obj in ordered_objects:
        if local_table_names:
            local_class = replace(
                obj._cls,
                datasource_alias=datasource_alias,
                table_name=obj.object_code,
                source_type="DB",
            )
            local_relations = [
                Relation(
                    from_object=getattr(rel, "from_object", "") or getattr(rel, "source_class", ""),
                    to_object=getattr(rel, "to_object", "") or getattr(rel, "target_class", ""),
                    cardinality=getattr(rel, "cardinality", "")
                    or getattr(rel, "relation_type", ""),
                    join_keys=list(getattr(rel, "join_keys", []) or []),
                    description=getattr(rel, "description", ""),
                )
                for rel in ordered_relations
                if (getattr(rel, "from_object", "") or getattr(rel, "source_class", ""))
                == obj.object_code
                or (getattr(rel, "to_object", "") or getattr(rel, "target_class", ""))
                == obj.object_code
            ]
            sliced_objects.append(
                Object(local_class, local_relations, loader=getattr(view, "_loader", None))
            )
        else:
            sliced_objects.append(obj)

    sliced_view = View(
        view_id=getattr(view, "view_id", ""),
        view_name=getattr(view, "view_name", ""),
        description=getattr(view, "description", ""),
        objects=sliced_objects,
        relations=ordered_relations,
        loader=getattr(view, "_loader", None),
    )
    sliced_view.fields = view_fields
    sliced_view.actions = list(getattr(view, "actions", []) or [])
    return sliced_view
