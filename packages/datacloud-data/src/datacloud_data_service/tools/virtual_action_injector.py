"""虚拟动作注入器：为 DB/KB 对象及 DB 视图注入 query_*/compute_*/search_* 虚拟动作。

改造要点：
- 按字段元数据规则自动推导并生成多个虚拟动作
    - DB 对象 → query_*（明细检索）；若存在度量字段 → 同时生成 compute_*（分组统计）
    - DYNAMIC_TABLE 对象 → query_* + compute_* + insert_* + update_* + delete_*
- DB 视图 → query_* + compute_*
    - KB 对象 → search_* + write_*
- 注入幂等：同名动作不重复追加
- 同时注册到全局 VirtualActionRegistry，供 MCP 路由使用
- 动作字段统一使用字段编码（field_code / property_code），不再使用中文名
- 虚拟工具前缀（query_/compute_）由 Settings 配置决定，可通过环境变量覆盖
"""

from __future__ import annotations

import logging
from typing import Any

from datacloud_data_service.config import get_settings

logger = logging.getLogger(__name__)


def inject_virtual_actions(loader: object) -> None:
    """
    为 Loader 中所有 DB/KB 对象及 DB 视图注入虚拟动作。

    注入结果：
    - DB 对象：query_{object_code}（+compute_{object_code} 若有度量字段）
    - DB 视图：query_{view_code} + compute_{view_code}
    - KB 对象：search_{object_code}

    同时向 VirtualActionRegistry 注册路由条目。
    """
    from datacloud_data_sdk.virtual_action.registry import get_registry

    registry = get_registry()
    registry.clear()

    # ── 1. 对象级虚拟动作 ─────────────────────────────────────────────────────
    for cls in loader._classes.values():
        if cls.source_type not in ("DB", "DYNAMIC_TABLE", "KNOWLEDGE_BASE"):
            continue

        # 已存在的动作编码（幂等保护）
        existing_codes = {a.action_code for a in cls.actions}

        # 确保字段已填充 analytic 元数据（OWL 解析时已做，这里做兜底）
        _ensure_analytic_meta(cls.fields)

        if cls.source_type == "DB":
            _inject_db_object_actions(cls, existing_codes, registry)
        elif cls.source_type == "DYNAMIC_TABLE":
            _inject_dynamic_table_object_actions(cls, existing_codes, registry)
        elif cls.source_type == "KNOWLEDGE_BASE":
            _inject_kb_object_actions(cls, existing_codes, registry)

    # ── 2. 视图级虚拟动作 ─────────────────────────────────────────────────────
    _inject_view_actions(loader, registry)

    logger.info(
        "virtual_action_injector: 注册完成，共 %d 个工具",
        len(registry.all_tools()),
    )


# ── 内部辅助 ──────────────────────────────────────────────────────────────────


def _ensure_analytic_meta(fields: list) -> None:
    """若字段 analytic_role 未设置，尝试从旧字段类型兼容推断（降级规则）。"""
    from datacloud_data_sdk.virtual_action.rules import derive_field_ops, infer_secondary_role

    for f in fields:
        if f.analytic_role is not None:
            continue  # 已由 OWL 解析器设置
        # 兼容旧字段：根据 field_type 做最小推断
        ft = (f.field_type or "").upper()
        if ft in ("NUMBER", "INTEGER", "BIGINT", "DECIMAL", "DOUBLE", "FLOAT"):
            f.analytic_role = "measure"
            f.analytic_kind = "raw_number"
        elif ft in ("DATE", "DATETIME", "TIMESTAMP"):
            f.analytic_role = "dimension"
            f.analytic_kind = "datetime"
        elif f.is_primary_key:
            f.analytic_role = "dimension"
            f.analytic_kind = "id"
        else:
            f.analytic_role = "dimension"
            f.analytic_kind = "name"
        # 派生操作符
        term_type = getattr(f, "term_type", None)
        f.filter_ops, f.group_ops, f.aggregate_ops, f.required_filter_group = derive_field_ops(
            f.analytic_role, f.analytic_kind, term_type=term_type
        )
        f.secondary_role = infer_secondary_role(f.analytic_role, f.analytic_kind)


def _required_filter_groups(fields: list) -> list[str]:
    """收集字段中出现的强制过滤组。"""
    groups: list[str] = []
    seen: set[str] = set()
    for f in fields:
        g = getattr(f, "required_filter_group", None)
        if g and g not in seen:
            groups.append(g)
            seen.add(g)
    return groups


def _has_measure(fields: list) -> bool:
    return any(
        getattr(f, "analytic_role", None) == "measure" and getattr(f, "aggregate_ops", [])
        for f in fields
    )


def _make_action(
    *,
    action_code: str,
    action_name: str,
    description: str,
    belong_class: str,
    action_family: str,
    virtual_backend: str,
    scope_type: str,
    scope_code: str,
    input_schema: dict,
    exposure_policy: str = "direct",
    legacy_aliases: list[str] | None = None,
    action_type: str = "query",
) -> Any:
    from datacloud_data_sdk.ontology.models import OntologyAction

    return OntologyAction(
        action_code=action_code,
        action_name=action_name,
        description=description,
        belong_class=belong_class,
        params=[],
        function_refs=[],
        action_type=action_type,
        is_virtual=True,
        input_schema=input_schema,
        output_schema={
            "type": "object",
            "properties": {
                "records": {"type": "array", "items": {"type": "object"}},
                "total": {"type": "integer"},
            },
        },
        action_family=action_family,
        virtual_backend=virtual_backend,
        scope_type=scope_type,
        scope_code=scope_code,
        exposure_policy=exposure_policy,
        planner_visible=True,
        legacy_aliases=legacy_aliases or [],
    )


def _inject_db_object_actions(cls, existing_codes: set, registry) -> None:
    """为 DB 对象注入 query_* 及可选的 compute_* 动作。"""
    from datacloud_data_sdk.virtual_action.generator import (
        build_compute_description,
        build_compute_schema,
        build_query_description,
        build_query_schema,
    )
    from datacloud_data_sdk.virtual_action.registry import ActionRoute

    settings = get_settings()
    obj_code = cls.object_code
    obj_name = cls.object_name or obj_code
    obj_desc = cls.description or ""
    fields = cls.fields
    req_groups = _required_filter_groups(fields)

    # query
    query_code = f"{settings.virtual_action_query_prefix}{obj_code}"
    if query_code not in existing_codes:
        schema = build_query_schema(
            obj_name,
            fields,
            req_groups,
            scope_type="object",
            scope_code=obj_code,
        )
        action = _make_action(
            action_code=query_code,
            action_name=f"查询{obj_name}明细",
            description=build_query_description(obj_name, obj_desc, fields, req_groups, "object"),
            belong_class=obj_code,
            action_family="query",
            virtual_backend="db_lookup",
            scope_type="object",
            scope_code=obj_code,
            input_schema=schema,
        )
        cls.actions.append(action)
        registry.register(query_code, ActionRoute("object", obj_code, "query"))
        logger.debug("注入 %s", query_code)

    # compute（仅当存在度量字段时）
    if _has_measure(fields):
        compute_code = f"{settings.virtual_action_compute_prefix}{obj_code}"
        if compute_code not in existing_codes:
            schema = build_compute_schema(
                obj_name,
                fields,
                req_groups,
                scope_type="object",
                scope_code=obj_code,
            )
            action = _make_action(
                action_code=compute_code,
                action_name=f"统计{obj_name}",
                description=build_compute_description(
                    obj_name, obj_desc, fields, req_groups, "object"
                ),
                belong_class=obj_code,
                action_family="compute",
                virtual_backend="db_analyze",
                scope_type="object",
                scope_code=obj_code,
                input_schema=schema,
            )
            cls.actions.append(action)
            registry.register(compute_code, ActionRoute("object", obj_code, "compute"))
            logger.debug("注入 %s", compute_code)


def _inject_dynamic_table_object_actions(cls, existing_codes: set, registry) -> None:
    """为 DYNAMIC_TABLE 对象注入 query/compute/insert/update/delete 动作。"""
    from datacloud_data_sdk.virtual_action.generator import (
        build_compute_description,
        build_compute_schema,
        build_delete_schema,
        build_insert_schema,
        build_query_description,
        build_query_schema,
        build_update_schema,
    )
    from datacloud_data_sdk.virtual_action.registry import ActionRoute

    settings = get_settings()
    obj_code = cls.object_code
    obj_name = cls.object_name or obj_code
    obj_desc = cls.description or ""
    fields = cls.fields
    req_groups = _required_filter_groups(fields)

    query_code = f"{settings.virtual_action_query_prefix}{obj_code}"
    if query_code not in existing_codes:
        action = _make_action(
            action_code=query_code,
            action_name=f"查询{obj_name}明细",
            description=build_query_description(obj_name, obj_desc, fields, req_groups, "object"),
            belong_class=obj_code,
            action_family="query",
            virtual_backend="dynamic_table_connector",
            scope_type="object",
            scope_code=obj_code,
            input_schema=build_query_schema(
                obj_name,
                fields,
                req_groups,
                scope_type="object",
                scope_code=obj_code,
            ),
        )
        cls.actions.append(action)
        registry.register(query_code, ActionRoute("object", obj_code, "query"))
        logger.debug("注入 %s", query_code)

    if _has_measure(fields):
        compute_code = f"{settings.virtual_action_compute_prefix}{obj_code}"
        if compute_code not in existing_codes:
            action = _make_action(
                action_code=compute_code,
                action_name=f"统计{obj_name}",
                description=build_compute_description(
                    obj_name, obj_desc, fields, req_groups, "object"
                ),
                belong_class=obj_code,
                action_family="compute",
                virtual_backend="dynamic_table_connector",
                scope_type="object",
                scope_code=obj_code,
                input_schema=build_compute_schema(
                    obj_name,
                    fields,
                    req_groups,
                    scope_type="object",
                    scope_code=obj_code,
                ),
            )
            cls.actions.append(action)
            registry.register(compute_code, ActionRoute("object", obj_code, "compute"))
            logger.debug("注入 %s", compute_code)

    operation_specs = [
        ("insert", f"insert_{obj_code}", f"新增{obj_name}", build_insert_schema(obj_name, fields)),
        ("update", f"update_{obj_code}", f"修改{obj_name}", build_update_schema(obj_name, fields)),
        ("delete", f"delete_{obj_code}", f"删除{obj_name}", build_delete_schema(obj_name, fields)),
    ]
    for action_family, action_code, action_name, input_schema in operation_specs:
        if action_code in existing_codes:
            continue
        action = _make_action(
            action_code=action_code,
            action_name=action_name,
            description=input_schema.get("description", action_name),
            belong_class=obj_code,
            action_family=action_family,
            virtual_backend="dynamic_table_connector",
            scope_type="object",
            scope_code=obj_code,
            input_schema=input_schema,
            action_type="operation",
        )
        cls.actions.append(action)
        registry.register(action_code, ActionRoute("object", obj_code, action_family))
        logger.debug("注入 %s", action_code)


def _inject_kb_object_actions(cls, existing_codes: set, registry) -> None:
    """为 KB 对象注入 search_* 和 write_* 动作。"""
    from datacloud_data_sdk.virtual_action.generator import (
        build_kb_write_schema,
        build_search_description,
        build_search_schema,
    )
    from datacloud_data_sdk.virtual_action.registry import ActionRoute

    obj_code = cls.object_code
    obj_name = cls.object_name or obj_code
    obj_desc = cls.description or ""
    search_code = f"search_{obj_code}"
    if search_code not in existing_codes:
        schema = build_search_schema(obj_name, cls.fields)
        action = _make_action(
            action_code=search_code,
            action_name=f"检索{obj_name}",
            description=build_search_description(obj_name, obj_desc, cls.fields),
            belong_class=obj_code,
            action_family="search",
            virtual_backend="kb_search",
            scope_type="object",
            scope_code=obj_code,
            input_schema=schema,
            legacy_aliases=[f"query_{obj_code}"],
        )
        cls.actions.append(action)
        registry.register(search_code, ActionRoute("object", obj_code, "search"))
        logger.debug("注入 %s", search_code)

    write_code = f"write_{obj_code}"
    if write_code not in existing_codes:
        schema = build_kb_write_schema(obj_name, cls.fields)
        action = _make_action(
            action_code=write_code,
            action_name=f"写入{obj_name}",
            description=schema.get("description", f"写入{obj_name}"),
            belong_class=obj_code,
            action_family="write",
            virtual_backend="kb_search",
            scope_type="object",
            scope_code=obj_code,
            input_schema=schema,
            action_type="operation",
        )
        cls.actions.append(action)
        registry.register(write_code, ActionRoute("object", obj_code, "write"))
        logger.debug("注入 %s", write_code)

    legacy_code = f"query_{obj_code}"
    if not registry.get(legacy_code):
        registry.register(legacy_code, ActionRoute("object", obj_code, "search"))


def _inject_view_actions(loader, registry) -> None:
    """为所有 DB 视图注入 query_* + compute_* 动作，挂载到 View.actions。"""
    from datacloud_data_sdk.virtual_action.generator import (
        build_compute_description,
        build_compute_schema,
        build_query_description,
        build_query_schema,
    )
    from datacloud_data_sdk.virtual_action.registry import ActionRoute

    settings = get_settings()
    scenes = getattr(loader, "_scenes", {})
    for view_id, scene in scenes.items():
        # 只处理 DB 视图（有对象列表的场景）
        raw_objects = (
            scene.get("object_codes") or scene.get("objects") or scene.get("object_ids") or []
        )
        if not raw_objects:
            continue
        # 归一化：支持 ["code"] 和 [{"object_code": "code"}] 两种格式
        object_codes = [
            oc if isinstance(oc, str) else oc.get("object_code", "") for oc in raw_objects
        ]
        object_codes = [oc for oc in object_codes if oc]
        if not object_codes:
            continue

        # 检查是否所有对象都是 DB 类型
        all_db = all(
            loader._classes.get(oc, None) is not None and loader._classes[oc].source_type == "DB"
            for oc in object_codes
        )
        if not all_db:
            continue

        # 获取视图字段（从 scene 中的 fields 或 mappings）
        view_fields = _extract_view_fields(scene, loader)
        if not view_fields:
            # 没有视图字段定义时，从第一个对象的字段合成
            first_cls = loader._classes.get(object_codes[0])
            if first_cls:
                _ensure_analytic_meta(first_cls.fields)
                view_fields = first_cls.fields
        else:
            # 回写标准化后的视图字段，保证 View.fields 与工具 schema 一致
            scene["fields"] = view_fields

        view_name = scene.get("view_name") or scene.get("name") or view_id
        view_desc = scene.get("description") or ""
        req_groups = _required_filter_groups(view_fields)

        # 获取或创建视图 actions 列表（存储在 scene 中，View 实例化时读取）
        view_actions = scene.setdefault("_virtual_actions", [])
        existing_codes = {a.action_code for a in view_actions}

        # query
        query_code = f"{settings.virtual_action_query_prefix}{view_id}"
        if query_code not in existing_codes:
            schema = build_query_schema(
                view_name,
                view_fields,
                req_groups,
                scope_type="view",
                scope_code=view_id,
            )
            action = _make_action(
                action_code=query_code,
                action_name=f"查询{view_name}明细",
                description=build_query_description(
                    view_name, view_desc, view_fields, req_groups, "view"
                ),
                belong_class=view_id,
                action_family="query",
                virtual_backend="db_lookup",
                scope_type="view",
                scope_code=view_id,
                input_schema=schema,
            )
            view_actions.append(action)
            registry.register(query_code, ActionRoute("view", view_id, "query"))
            logger.debug("注入视图 %s", query_code)

        # compute
        if _has_measure(view_fields):
            compute_code = f"{settings.virtual_action_compute_prefix}{view_id}"
            if compute_code not in existing_codes:
                schema = build_compute_schema(
                    view_name,
                    view_fields,
                    req_groups,
                    scope_type="view",
                    scope_code=view_id,
                )
                action = _make_action(
                    action_code=compute_code,
                    action_name=f"统计{view_name}",
                    description=build_compute_description(
                        view_name, view_desc, view_fields, req_groups, "view"
                    ),
                    belong_class=view_id,
                    action_family="compute",
                    virtual_backend="db_analyze",
                    scope_type="view",
                    scope_code=view_id,
                    input_schema=schema,
                )
                view_actions.append(action)
                registry.register(compute_code, ActionRoute("view", view_id, "compute"))
                logger.debug("注入视图 %s", compute_code)


def _resolve_source_field_type(
    loader: Any, source_object_code: str, source_column_code: str
) -> str | None:
    """根据视图映射回查源对象字段类型。"""
    field = _resolve_source_field(loader, source_object_code, source_column_code)
    return getattr(field, "field_type", None) if field is not None else None


def _resolve_source_field(
    loader: Any, source_object_code: str, source_column_code: str
) -> Any | None:
    """根据视图映射回查源对象字段。"""
    if not source_object_code or not source_column_code:
        return None
    try:
        cls = loader.get_ontology_class(source_object_code)
    except Exception:
        return None

    for field in getattr(cls, "fields", []):
        if (
            field.field_code == source_column_code
            or getattr(field, "source_column", None) == source_column_code
        ):
            return field
    return None


def _apply_source_term_meta(view_field: Any, source_field: Any | None) -> None:
    """将源字段术语元数据复制到视图字段。"""
    if source_field is None:
        return
    view_field.term_set = getattr(source_field, "term_set", None)
    view_field.term_type = getattr(source_field, "term_type", None)
    view_field.term_field = getattr(source_field, "term_field", None)
    view_field.dataset_id = getattr(source_field, "dataset_id", None)


def _extract_view_fields(scene: dict, loader: Any) -> list:
    """
    从 scene 字典中提取视图字段元数据。

    优先顺序：
    1. scene["fields"]（ViewFieldMeta 列表，由 OWL 解析器填充）
    2. scene["mappings"]（mapping OWL 解析产物）
    3. 空列表（由调用方降级到对象字段）
    """
    from datacloud_data_sdk.virtual_action.models import ViewFieldMeta
    from datacloud_data_sdk.virtual_action.rules import (
        derive_field_ops,
        infer_secondary_role,
        parse_analytic_role,
    )

    # 优先使用已解析的 ViewFieldMeta 列表
    if "fields" in scene and scene["fields"]:
        raw_fields = scene["fields"]
        result: list = []
        for rf in raw_fields:
            if isinstance(rf, ViewFieldMeta):
                if rf.secondary_role is None:
                    rf.secondary_role = infer_secondary_role(rf.analytic_role, rf.analytic_kind)
                _apply_source_term_meta(
                    rf,
                    _resolve_source_field(
                        loader,
                        rf.source_object_code,
                        rf.source_object_column_code,
                    ),
                )
                result.append(rf)
            elif isinstance(rf, dict):
                role, kind = parse_analytic_role(rf.get("ext_property") or "")
                fops, gops, aops, rfg = derive_field_ops(role, kind)
                source_field = _resolve_source_field(
                    loader,
                    rf.get("source_object_code", ""),
                    rf.get("source_object_column_code", ""),
                )
                vf = ViewFieldMeta(
                    property_code=rf.get("property_code", ""),
                    property_name=rf.get("property_name", ""),
                    source_object_code=rf.get("source_object_code", ""),
                    source_object_column_code=rf.get("source_object_column_code", ""),
                    field_type=rf.get("field_type")
                    or _resolve_source_field_type(
                        loader,
                        rf.get("source_object_code", ""),
                        rf.get("source_object_column_code", ""),
                    ),
                    analytic_role=role,
                    analytic_kind=kind,
                    secondary_role=infer_secondary_role(role, kind),
                    filter_ops=fops,
                    group_ops=gops,
                    aggregate_ops=aops,
                    required_filter_group=rfg,
                )
                _apply_source_term_meta(vf, source_field)
                result.append(vf)
        return result

    # 从 mappings 构建
    if "mappings" in scene and scene["mappings"]:
        result = []
        for m in scene["mappings"]:
            if isinstance(m, dict):
                role, kind = parse_analytic_role(m.get("ext_property") or "")
                fops, gops, aops, rfg = derive_field_ops(role, kind)
                source_field = _resolve_source_field(
                    loader,
                    m.get("source_object_code", ""),
                    m.get("source_object_column_code", ""),
                )
                vf = ViewFieldMeta(
                    property_code=m.get("property_code", ""),
                    property_name=m.get("property_name", ""),
                    source_object_code=m.get("source_object_code", ""),
                    source_object_column_code=m.get("source_object_column_code", ""),
                    field_type=m.get("field_type")
                    or _resolve_source_field_type(
                        loader,
                        m.get("source_object_code", ""),
                        m.get("source_object_column_code", ""),
                    ),
                    analytic_role=role,
                    analytic_kind=kind,
                    secondary_role=infer_secondary_role(role, kind),
                    filter_ops=fops,
                    group_ops=gops,
                    aggregate_ops=aops,
                    required_filter_group=rfg,
                )
                _apply_source_term_meta(vf, source_field)
                result.append(vf)
        return result

    return []
