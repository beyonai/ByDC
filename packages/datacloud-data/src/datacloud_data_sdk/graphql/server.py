"""GraphQL 服务：从 OntologyLoader 生成 Strawberry schema 并暴露 HTTP 端点。"""

from __future__ import annotations

import ast
import inspect
from typing import TYPE_CHECKING, Any, get_args, get_origin

if TYPE_CHECKING:
    from datacloud_data_sdk.ontology.loader import OntologyLoader
    from datacloud_data_sdk.sql_executor.data_source_manager import DataSourceManager

# field_type -> Python 类型（用于 Strawberry 注解）
_FIELD_TYPE_TO_PY = {
    "STRING": str,
    "NUMBER": float,
    "INTEGER": int,
    "BOOLEAN": bool,
    "DATE": str,
    "DATETIME": str,
    "ARRAY": str,
    "OBJECT": str,
}


def _to_pascal_case(snake: str) -> str:
    """snake_case -> PascalCase。"""
    components = snake.split("_")
    return "".join(x.title() for x in components if x)


def _field_type_to_python(field_type: str) -> type:
    """本体 field_type 映射到 Python 类型。"""
    return _FIELD_TYPE_TO_PY.get(field_type.upper(), str)


def _topological_sort_classes(
    classes: list[Any],
    loader: OntologyLoader,
) -> list[Any]:
    """按依赖排序：linked 的 target 在 source 之前。"""
    class_by_code = {c.object_code: c for c in classes}
    relations = loader.get_ontology_relations()
    rel_by_code = {r.relation_code: r for r in relations}

    # 构建依赖：source 依赖 target（target 需先创建）
    deps: dict[str, set[str]] = {c.object_code: set() for c in classes}
    for cls in classes:
        for f in cls.fields:
            if getattr(f, "property_kind", "physical") != "linked":
                continue
            ref = getattr(f, "relation_ref", None)
            if not ref:
                continue
            rel = rel_by_code.get(ref)
            if rel and rel.target_class in class_by_code and rel.target_class != cls.object_code:
                deps[cls.object_code].add(rel.target_class)

    result: list[Any] = []
    remaining = set(c.object_code for c in classes)
    while remaining:
        ready = [c for c in remaining if not deps[c] & remaining]
        if not ready:
            break
        for code in sorted(ready):
            result.append(class_by_code[code])
            remaining.discard(code)
    # 未处理的按原序追加
    for c in classes:
        if c.object_code not in [x.object_code for x in result]:
            result.append(c)
    return result


def _create_strawberry_type_from_class(
    ontology_class: Any,
    type_map: dict[str, type],
    loader: OntologyLoader,
    ds_manager: DataSourceManager | None,
) -> type:
    """从 OntologyClass 动态创建 Strawberry 类型。支持 physical、linked、derived。"""
    import strawberry

    from datacloud_data_sdk.executor.linked_resolver import (
        resolve_api_linked_batch,
        resolve_db_linked_batch,
    )

    attrs: dict[str, Any] = {"__annotations__": {}}
    relations = loader.get_ontology_relations()
    rel_by_code = {r.relation_code: r for r in relations}

    def make_linked_field_resolver(
        field: Any,
        relation: Any,
        target_strawberry_type: type,
    ):
        field_code = field.field_code

        async def _resolver(root: Any, info: strawberry.Info) -> list:
            # 同源 DB 已填充：root 上已有值
            val = getattr(root, field_code, None)
            if val is not None and isinstance(val, list):
                return val

            # 从 root 构建 parent_dict
            ann = getattr(type(root), "__annotations__", {})
            parent_dict = {k: getattr(root, k, None) for k in ann.keys()}

            ctx = info.context
            loader_ctx = ctx.get("loader")
            ds_ctx = ctx.get("ds_manager")

            if not loader_ctx:
                return []

            if relation.resolve_action_code:
                batches = await resolve_api_linked_batch(loader_ctx, [parent_dict], field, relation)
            else:
                if not ds_ctx:
                    return []
                batches = await resolve_db_linked_batch(
                    loader_ctx, [parent_dict], field, relation, ds_ctx
                )

            raw_list = batches[0] if batches else []
            return [
                _record_to_strawberry(r, target_strawberry_type, type_map, loader) for r in raw_list
            ]

        return strawberry.field(resolver=_resolver)

    def make_derived_field_resolver(field_code: str, field: Any, source_class: str):
        async def _resolver(root: Any, info: strawberry.Info) -> Any:
            # 同源 DB 已计算：直接返回
            val = getattr(root, field_code, None)
            if val is not None:
                return val

            dc = getattr(field, "derived_config", None) or {}
            mode = dc.get("mode")

            if mode == "expression":
                expr = dc.get("expression", "")
                depends_on = dc.get("depends_on", [])
                scope: dict[str, Any] = {}
                for dep in depends_on:
                    scope[dep] = getattr(root, dep, None)
                try:
                    # 安全计算：仅支持简单算术
                    tree = ast.parse(expr, mode="eval")
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.Call, ast.Attribute, ast.Subscript)):
                            raise ValueError("Unsupported expression")
                    return eval(expr, {"__builtins__": {}}, scope)
                except Exception:
                    return None

            if mode == "aggregation":
                relation_ref = dc.get("relation_ref")
                if not relation_ref:
                    return None
                rel = next((r for r in relations if r.relation_code == relation_ref), None)
                if not rel:
                    return None
                target_field = dc.get("target_field", "id")
                func = (dc.get("func") or "count").lower()

                # 先 resolve linked（需构造虚拟 field 供 LinkedResolver）
                from datacloud_data_sdk.ontology.models import OntologyField

                agg_field = OntologyField(
                    field_code="_agg",
                    field_name="",
                    field_type="ARRAY",
                    relation_ref=relation_ref,
                )
                ann = getattr(type(root), "__annotations__", {})
                parent_dict = {k: getattr(root, k, None) for k in ann.keys()}
                loader_ctx = info.context.get("loader")
                ds_ctx = info.context.get("ds_manager")

                if rel.resolve_action_code:
                    batches = await resolve_api_linked_batch(
                        loader_ctx, [parent_dict], agg_field, rel
                    )
                else:
                    if not ds_ctx:
                        return 0
                    batches = await resolve_db_linked_batch(
                        loader_ctx, [parent_dict], agg_field, rel, ds_ctx
                    )

                linked_list = batches[0] if batches else []
                if func == "count":
                    return len(linked_list)
                if func == "sum":
                    return sum(
                        (r.get(target_field) or 0)
                        for r in linked_list
                        if isinstance(r.get(target_field), (int, float))
                    )
                return len(linked_list)

            return None

        return strawberry.field(resolver=_resolver)

    for f in ontology_class.fields:
        kind = getattr(f, "property_kind", "physical")

        if kind == "linked":
            relation_ref = getattr(f, "relation_ref", None)
            rel = rel_by_code.get(relation_ref) if relation_ref else None
            if not rel:
                attrs["__annotations__"][f.field_code] = list[Any] | None
                attrs[f.field_code] = None
                continue
            target_type = type_map.get(rel.target_class)
            if not target_type:
                attrs["__annotations__"][f.field_code] = list[Any] | None
                attrs[f.field_code] = None
                continue
            attrs["__annotations__"][f.field_code] = list[target_type]
            attrs[f.field_code] = make_linked_field_resolver(f, rel, target_type)

        elif kind == "derived":
            py_type = _field_type_to_python(f.field_type)
            attrs["__annotations__"][f.field_code] = py_type | None
            attrs[f.field_code] = make_derived_field_resolver(
                f.field_code, f, ontology_class.object_code
            )

        else:
            py_type = _field_type_to_python(f.field_type)
            attrs["__annotations__"][f.field_code] = py_type | None
            attrs[f.field_code] = None

    name = _to_pascal_case(ontology_class.object_code)
    return strawberry.type(type(name, (), attrs))


def _record_to_strawberry(
    record: dict[str, Any],
    strawberry_type: type,
    type_map: dict[str, type] | None = None,
    loader: OntologyLoader | None = None,
) -> Any:
    """将 record dict 映射为 Strawberry 类型实例。linked 嵌套 list 会转换为 target 类型。"""

    ann = getattr(strawberry_type, "__annotations__", {})
    type_map = type_map or {}

    # Strawberry 类型 __init__ 只接受非 resolver 字段；resolver 字段需在构造后设置
    init_params = set(inspect.signature(strawberry_type.__init__).parameters) - {"self"}

    init_attrs: dict[str, Any] = {}
    post_attrs: dict[str, Any] = {}

    for k in ann.keys():
        val = record.get(k)
        if val is None:
            v = None
        else:
            annot = ann.get(k)
            origin = get_origin(annot) if annot else None
            if origin is list and isinstance(val, list) and val and isinstance(val[0], dict):
                args = get_args(annot) if annot else ()
                inner_type = args[0] if args else None
                v = (
                    [_record_to_strawberry(r, inner_type, type_map, loader) for r in val]
                    if inner_type
                    else val
                )
            else:
                v = val

        if k in init_params:
            init_attrs[k] = v
        else:
            post_attrs[k] = v

    obj = strawberry_type(**init_attrs)
    for k, v in post_attrs.items():
        setattr(obj, k, v)
    return obj


def _create_query_type(
    loader: OntologyLoader,
    type_map: dict[str, type],
    classes: list[Any],
    ds_manager: DataSourceManager | None,
) -> type:
    """创建 Query 根类型：DB 对象用 {object}_list，API 对象用 {action_code}。"""
    import strawberry

    from datacloud_data_sdk.executor.dynamic_query_executor import DynamicQueryExecutor
    from datacloud_data_sdk.graphql.arg_converter import where_to_filters

    attrs: dict[str, Any] = {"__annotations__": {}}
    class_by_code = {c.object_code: c for c in classes}

    def make_db_list_resolver(object_code: str, strawberry_type: type):
        async def _resolver(
            root: None,
            info: strawberry.Info,
            where: str | None = None,
            limit: int | None = None,
            offset: int | None = None,
        ) -> list:
            import json

            ctx = info.context
            loader_ctx = ctx.get("loader")
            ds_ctx = ctx.get("ds_manager")
            if not loader_ctx:
                return []
            where_dict: dict = {}
            if where:
                try:
                    where_dict = json.loads(where) if isinstance(where, str) else (where or {})
                except (json.JSONDecodeError, TypeError):
                    where_dict = {}
            executor = DynamicQueryExecutor(loader_ctx, ds_manager=ds_ctx)
            arguments = {
                "filters": where_to_filters(where_dict),
                "limit": limit,
                "offset": offset,
            }
            result = await executor.execute(object_code, arguments)
            records = result.get("records", [])
            return [
                _record_to_strawberry(r, strawberry_type, type_map, loader_ctx) for r in records
            ]

        return strawberry.field(resolver=_resolver)

    def make_api_action_resolver(
        object_code: str,
        action_code: str,
        strawberry_type: type,
        in_params: list[tuple[str, type, bool]],
    ):
        param_names = [p[0] for p in in_params]

        async def _resolver(root: None, info: strawberry.Info, **kwargs: Any) -> list:
            ctx = info.context
            loader_ctx = ctx.get("loader")
            if not loader_ctx:
                return []
            obj = loader_ctx.get_object(object_code)
            params = {k: v for k, v in kwargs.items() if k in param_names and v is not None}
            result = await obj.invoke_action(action_code, params)
            records = result.get("records", []) if isinstance(result, dict) else []
            return [
                _record_to_strawberry(r, strawberry_type, type_map, loader_ctx) for r in records
            ]

        sig_params = [
            inspect.Parameter("root", inspect.Parameter.POSITIONAL_OR_KEYWORD),
            inspect.Parameter(
                "info", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=strawberry.Info
            ),
        ]
        for name, py_type, required in in_params:
            default = inspect.Parameter.empty if required else None
            sig_params.append(
                inspect.Parameter(
                    name,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    annotation=py_type,
                    default=default,
                )
            )
        _resolver.__signature__ = inspect.Signature(sig_params)
        return strawberry.field(resolver=_resolver)

    for object_code, strawberry_type in type_map.items():
        cls = class_by_code.get(object_code)
        if not cls:
            continue
        if cls.source_type == "DB":
            field_name = f"{object_code}_list"
            attrs["__annotations__"][field_name] = list[strawberry_type]
            attrs[field_name] = make_db_list_resolver(object_code, strawberry_type)
        elif cls.source_type == "API":
            relations = loader.get_ontology_relations()
            for action in cls.actions:
                if action.action_type != "query":
                    continue
                field_name = action.action_code
                rel = next(
                    (r for r in relations if r.resolve_action_code == action.action_code),
                    None,
                )
                out_class = rel.target_class if rel else object_code
                out_strawberry_type = type_map.get(out_class, strawberry_type)
                in_params = [
                    (p.param_code, _param_type_to_strawberry(p.param_type), p.required)
                    for p in action.params
                    if p.direction in ("IN", "INOUT")
                ]
                if field_name in attrs:
                    continue
                attrs["__annotations__"][field_name] = list[out_strawberry_type]
                attrs[field_name] = make_api_action_resolver(
                    object_code, action.action_code, out_strawberry_type, in_params
                )

    if not attrs["__annotations__"]:
        attrs["__annotations__"]["_ping"] = str
        attrs["_ping"] = strawberry.field(default="ok")

    return strawberry.type(type("Query", (), attrs))


def _param_type_to_strawberry(param_type: str) -> type:
    """action param_type 映射到 Strawberry 类型。"""
    m: dict[str, type] = {"STRING": str, "NUMBER": float, "INTEGER": int, "BOOLEAN": bool}
    return m.get(param_type.upper(), str)


def create_schema_from_loader(
    loader: OntologyLoader,
    ds_manager: DataSourceManager | None = None,
) -> Any:
    """从 OntologyLoader 生成 Strawberry Schema。

    Args:
        loader: 已加载本体的 OntologyLoader
        ds_manager: 数据源管理器，供 DB 对象 resolver 使用

    Returns:
        strawberry.Schema 实例
    """
    import strawberry

    classes = loader.get_ontology_classes()
    sorted_classes = _topological_sort_classes(classes, loader)
    type_map: dict[str, type] = {}
    for cls in sorted_classes:
        type_map[cls.object_code] = _create_strawberry_type_from_class(
            cls, type_map, loader, ds_manager
        )

    query_type = _create_query_type(loader, type_map, classes, ds_manager)
    return strawberry.Schema(query=query_type)


def get_graphql_router(
    loader: OntologyLoader,
    ds_manager: DataSourceManager | None = None,
) -> Any:
    """返回 FastAPI 可挂载的 GraphQL 路由。

    Args:
        loader: 已加载本体的 OntologyLoader（通常从 crm_demo_graphql 加载）
        ds_manager: 数据源管理器，供 DB 对象 resolver 使用

    Returns:
        strawberry.fastapi.GraphQLRouter 实例，可 include_router 到 FastAPI
    """
    from strawberry.fastapi import GraphQLRouter

    schema = create_schema_from_loader(loader, ds_manager)

    def _get_context():
        return {"loader": loader, "ds_manager": ds_manager}

    return GraphQLRouter(schema, path="/", context_getter=_get_context)
