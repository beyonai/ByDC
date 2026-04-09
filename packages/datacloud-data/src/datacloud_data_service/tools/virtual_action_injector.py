"""虚拟动作注入器：为 DB/KB 对象及 DB 视图注入 lookup_*/analyze_*/search_* 虚拟动作。

改造要点：
- 按字段元数据规则自动推导并生成多个虚拟动作（不再统一命名为 query_*）
- DB 对象 → lookup_*；若存在度量字段 → 同时生成 analyze_*
- DB 视图 → lookup_* + analyze_*
- KB 对象 → search_*
- 旧 query_* 动作保留为兼容别名（标记为 legacy_aliases）
- 注入幂等：同名动作不重复追加
- 同时注册到全局 VirtualActionRegistry，供 MCP 路由使用
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def inject_virtual_actions(loader: object) -> None:
    """
    为 Loader 中所有 DB/KB 对象及 DB 视图注入虚拟动作。

    注入结果：
    - DB 对象：lookup_{object_code}（+analyze_{object_code} 若有度量字段）
    - DB 视图：lookup_{view_code} + analyze_{view_code}
    - KB 对象：search_{object_code}

    同时向 VirtualActionRegistry 注册路由条目。
    """
    from datacloud_data_sdk.virtual_action.registry import get_registry

    registry = get_registry()
    registry.clear()

    # ── 1. 对象级虚拟动作 ─────────────────────────────────────────────────────
    for cls in loader._classes.values():
        if cls.source_type not in ("DB", "KNOWLEDGE_BASE"):
            continue

        # 已存在的动作编码（幂等保护）
        existing_codes = {a.action_code for a in cls.actions}

        # 确保字段已填充 analytic 元数据（OWL 解析时已做，这里做兜底）
        _ensure_analytic_meta(cls.fields)

        if cls.source_type == "DB":
            _inject_db_object_actions(cls, existing_codes, registry)
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
            f.analytic_kind = "number"
        elif ft in ("DATE", "DATETIME", "TIMESTAMP"):
            f.analytic_role = "dimension"
            f.analytic_kind = "time"
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
) -> Any:
    from datacloud_data_sdk.ontology.models import OntologyAction

    return OntologyAction(
        action_code=action_code,
        action_name=action_name,
        description=description,
        belong_class=belong_class,
        params=[],
        function_refs=[],
        action_type="query",
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
    """为 DB 对象注入 lookup_* 及可选的 analyze_* 动作。"""
    from datacloud_data_sdk.virtual_action.generator import (
        build_analyze_schema, build_lookup_schema,
        build_lookup_description, build_analyze_description,
    )
    from datacloud_data_sdk.virtual_action.registry import ActionRoute

    obj_code = cls.object_code
    obj_name = cls.object_name or obj_code
    obj_desc = cls.description or ""
    fields = cls.fields
    req_groups = _required_filter_groups(fields)

    # lookup
    lookup_code = f"lookup_{obj_code}"
    if lookup_code not in existing_codes:
        schema = build_lookup_schema(obj_name, fields, req_groups)
        action = _make_action(
            action_code=lookup_code,
            action_name=f"查询{obj_name}明细",
            description=build_lookup_description(obj_name, obj_desc, fields, req_groups, "object"),
            belong_class=obj_code,
            action_family="lookup",
            virtual_backend="db_lookup",
            scope_type="object",
            scope_code=obj_code,
            input_schema=schema,
            legacy_aliases=[f"query_{obj_code}"],
        )
        cls.actions.append(action)
        registry.register(lookup_code, ActionRoute("object", obj_code, "lookup"))
        logger.debug("注入 %s", lookup_code)

    # analyze（仅当存在度量字段时）
    if _has_measure(fields):
        analyze_code = f"analyze_{obj_code}"
        if analyze_code not in existing_codes:
            schema = build_analyze_schema(obj_name, fields, req_groups)
            action = _make_action(
                action_code=analyze_code,
                action_name=f"统计{obj_name}",
                description=build_analyze_description(obj_name, obj_desc, fields, req_groups, "object"),
                belong_class=obj_code,
                action_family="analyze",
                virtual_backend="db_analyze",
                scope_type="object",
                scope_code=obj_code,
                input_schema=schema,
            )
            cls.actions.append(action)
            registry.register(analyze_code, ActionRoute("object", obj_code, "analyze"))
            logger.debug("注入 %s", analyze_code)

    # 旧 query_* 兼容：注册路由到 lookup（已存在则跳过）
    legacy_code = f"query_{obj_code}"
    if legacy_code not in existing_codes and not registry.get(legacy_code):
        registry.register(legacy_code, ActionRoute("object", obj_code, "lookup"))


def _inject_kb_object_actions(cls, existing_codes: set, registry) -> None:
    """为 KB 对象注入 search_* 动作。"""
    from datacloud_data_sdk.virtual_action.generator import build_search_schema, build_search_description
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

    legacy_code = f"query_{obj_code}"
    if not registry.get(legacy_code):
        registry.register(legacy_code, ActionRoute("object", obj_code, "search"))


def _inject_view_actions(loader, registry) -> None:
    """为所有 DB 视图注入 lookup_* + analyze_* 动作，挂载到 View.actions。"""
    from datacloud_data_sdk.virtual_action.generator import (
        build_analyze_schema, build_lookup_schema,
        build_lookup_description, build_analyze_description,
    )
    from datacloud_data_sdk.virtual_action.registry import ActionRoute

    scenes = getattr(loader, "_scenes", {})
    for view_id, scene in scenes.items():
        # 只处理 DB 视图（有对象列表的场景）
        raw_objects = scene.get("object_codes") or scene.get("objects") or scene.get("object_ids") or []
        if not raw_objects:
            continue
        # 归一化：支持 ["code"] 和 [{"object_code": "code"}] 两种格式
        object_codes = [
            oc if isinstance(oc, str) else oc.get("object_code", "")
            for oc in raw_objects
        ]
        object_codes = [oc for oc in object_codes if oc]
        if not object_codes:
            continue

        # 检查是否所有对象都是 DB 类型
        all_db = all(
            loader._classes.get(oc, None) is not None
            and loader._classes[oc].source_type == "DB"
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

        # lookup
        lookup_code = f"lookup_{view_id}"
        if lookup_code not in existing_codes:
            schema = build_lookup_schema(view_name, view_fields, req_groups)
            action = _make_action(
                action_code=lookup_code,
                action_name=f"查询{view_name}明细",
                description=build_lookup_description(view_name, view_desc, view_fields, req_groups, "view"),
                belong_class=view_id,
                action_family="lookup",
                virtual_backend="db_lookup",
                scope_type="view",
                scope_code=view_id,
                input_schema=schema,
            )
            view_actions.append(action)
            registry.register(lookup_code, ActionRoute("view", view_id, "lookup"))
            logger.debug("注入视图 %s", lookup_code)

        # analyze
        if _has_measure(view_fields):
            analyze_code = f"analyze_{view_id}"
            if analyze_code not in existing_codes:
                schema = build_analyze_schema(view_name, view_fields, req_groups)
                action = _make_action(
                    action_code=analyze_code,
                    action_name=f"统计{view_name}",
                    description=build_analyze_description(view_name, view_desc, view_fields, req_groups, "view"),
                    belong_class=view_id,
                    action_family="analyze",
                    virtual_backend="db_analyze",
                    scope_type="view",
                    scope_code=view_id,
                    input_schema=schema,
                )
                view_actions.append(action)
                registry.register(analyze_code, ActionRoute("view", view_id, "analyze"))
                logger.debug("注入视图 %s", analyze_code)


def _resolve_source_field_type(loader: Any, source_object_code: str, source_column_code: str) -> str | None:
    """根据视图映射回查源对象字段类型。"""
    if not source_object_code or not source_column_code:
        return None
    try:
        cls = loader.get_ontology_class(source_object_code)
    except Exception:
        return None

    for field in getattr(cls, "fields", []):
        if field.field_code == source_column_code or getattr(field, "source_column", None) == source_column_code:
            return field.field_type
    return None


def _extract_view_fields(scene: dict, loader: Any) -> list:
    """
    从 scene 字典中提取视图字段元数据。

    优先顺序：
    1. scene["fields"]（ViewFieldMeta 列表，由 OWL 解析器填充）
    2. scene["mappings"]（mapping OWL 解析产物）
    3. 空列表（由调用方降级到对象字段）
    """
    from datacloud_data_sdk.virtual_action.models import ViewFieldMeta
    from datacloud_data_sdk.virtual_action.rules import parse_analytic_role, derive_field_ops

    # 优先使用已解析的 ViewFieldMeta 列表
    if "fields" in scene and scene["fields"]:
        raw_fields = scene["fields"]
        result: list = []
        for rf in raw_fields:
            if isinstance(rf, ViewFieldMeta):
                result.append(rf)
            elif isinstance(rf, dict):
                role, kind = parse_analytic_role(rf.get("ext_property") or "")
                fops, gops, aops, rfg = derive_field_ops(role, kind)
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
                    filter_ops=fops,
                    group_ops=gops,
                    aggregate_ops=aops,
                    required_filter_group=rfg,
                )
                result.append(vf)
        return result

    # 从 mappings 构建
    if "mappings" in scene and scene["mappings"]:
        result = []
        for m in scene["mappings"]:
            if isinstance(m, dict):
                role, kind = parse_analytic_role(m.get("ext_property") or "")
                fops, gops, aops, rfg = derive_field_ops(role, kind)
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
                    filter_ops=fops,
                    group_ops=gops,
                    aggregate_ops=aops,
                    required_filter_group=rfg,
                )
                result.append(vf)
        return result

    return []
