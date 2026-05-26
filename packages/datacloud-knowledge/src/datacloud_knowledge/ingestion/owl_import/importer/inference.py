"""外部 OWL 格式推断层 — 归一化格式差异 + 推断缺省关系。

本模块位于 OWL 解析器（owl_parser）与转换器（owl_converter）之间，
负责处理导入的外部 OWL 包与系统内部规范之间的格式差异：

1. source_type 归一化：中文别名映射为标准英文标识（补充缺失的"场景"→"view"）
2. joinkeys 字段名归一化：from_field → sourceField, to_field → targetField
3. term_code_path 小写化：OBJECT#code → object#code
4. 关系推断：当外部 OWL 包缺少独立的关系文件（_attribute_relations.owl 等）时，
   自动从 _definition.owl 的 EntityField/SceneField/object_codes 推断关系
5. Action 引用完整性校验：验证 action_refs 与 actions/ 目录下实际文件的一致性

Phase 1 中 Action 不落库，仅做文件级引用完整性校验。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── 格式归一化映射表 ──────────────────────────────────────────────────────────────

# source_type / target_type 中文别名 → 标准英文标识
# 外部 OWL 历史数据使用中文命名实体类型（"对象"/"视图"/"场景"/"属性"），
# 系统内部使用标准英文（object/view/prop/action）。
_SOURCE_TYPE_ALIAS: dict[str, str] = {
    "对象": "object",
    "视图": "view",
    "场景": "view",  # "场景" 是"视图"的历史别名
    "属性": "prop",
    "动作": "action",
    "术语类型": "term_type",
    "术语": "term_type",
}

# joinkeys 字段名归一化：外部 OWL 格式 → 系统标准字段名
# 外部 OWL 使用 from_field/to_field 命名 JOIN 键，
# 系统内部使用 sourceField/targetField 命名。
_JOINKEY_FIELD_ALIAS: dict[str, str] = {
    "from_field": "sourceField",
    "to_field": "targetField",
}


# ── 单实体格式化归一化 ────────────────────────────────────────────────────────────


def normalize_source_type(raw_type: str | None) -> str:
    """将中文 source_type / target_type 归一化为标准英文标识。

    业务逻辑：
    - "场景"/"视图" → "view"
    - "对象" → "object"
    - "属性" → "prop"
    - "动作" → "action"

    已为英文的值直接透传。
    """
    if not raw_type:
        return ""
    key = raw_type.strip()
    return _SOURCE_TYPE_ALIAS.get(key, key)


def normalize_term_code_path(raw_path: str | None) -> str:
    """将 term_code_path 归一化为小写：OBJECT#code → object#code。

    业务逻辑：
    - 外部 OWL 历史数据的 term_code_path 可能使用大写格式（OBJECT#by_customer）
    - 系统内部统一使用小写（object#by_customer）
    - 多级路径（object#code#prop#code）同样全部小写化
    """
    if not raw_path:
        return ""
    return raw_path.strip().lower()


def normalize_joinkeys(joinkeys: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """归一化 joinkeys 数组的字段名：from_field → sourceField, to_field → targetField。

    每个 joinkeys 项描述源表与目标表之间的 JOIN 键映射（仅 MANY_TO_ONE 关系有值）。
    外部 OWL 历史数据使用 from_field/to_field 命名，系统标准使用 sourceField/targetField。
    """
    if not joinkeys:
        return []

    normalized: list[dict[str, Any]] = []
    for jk in joinkeys:
        if not isinstance(jk, dict):
            continue
        njk: dict[str, Any] = {}
        for k, v in jk.items():
            njk[_JOINKEY_FIELD_ALIAS.get(k, k)] = v
        normalized.append(njk)
    return normalized


def normalize_entity(entity: dict[str, Any]) -> dict[str, Any]:
    """对单个 OWL 实体 dict 执行所有格式归一化。

    返回新 dict，不修改输入。

    归一化覆盖：
    1. source_type / target_type 中文→英文
    2. term_code_path / term_type_code_path 小写化
    3. joinkeys 字段名标准化（from_field → sourceField 等）
    4. term_type_code_path 小写化
    """
    result: dict[str, Any] = {}

    for key, value in entity.items():
        # 1. source_type / target_type 类型归一化
        if key in ("source_type", "target_type"):
            result[key] = normalize_source_type(str(value)) if value else ""

        # 2. term_code_path / term_type_code_path 小写化
        elif key in ("term_code_path", "term_type_code_path"):
            result[key] = normalize_term_code_path(str(value)) if value else ""

        # 3. joinkeys 归一化
        elif key == "joinkeys":
            jk_value: Any = value
            if isinstance(jk_value, str):
                try:
                    jk_value = json.loads(jk_value)
                except (json.JSONDecodeError, TypeError):
                    logger.warning(
                        "joinkeys JSON 解析失败: entity_type=%s, value=%s",
                        entity.get("entity_type", ""),
                        str(jk_value)[:100],
                    )
                    jk_value = []
            result[key] = normalize_joinkeys(jk_value if isinstance(jk_value, list) else [])

        else:
            result[key] = value

    return result


def normalize_entities(entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """对实体列表批量执行格式归一化。

    每个实体独立归一化，不修改输入列表。
    """
    return [normalize_entity(e) for e in entities]


# ── Action 引用完整性校验 ─────────────────────────────────────────────────────────


def validate_action_refs(entities: list[dict[str, Any]], actions_dir: Path) -> list[str]:
    """验证 action_refs 与 actions/ 目录下文件的引用完整性。

    业务逻辑：
    - 外部平台在 EntityDefinition 的 action_refs 字段中声明该对象关联的 Action
    - 导入前校验每个被引用的 action_code 在 actions/ 目录下是否有对应的 .owl 文件
    - Phase 1 Action 不落库，仅做文件级引用完整性校验

    校验时机：
    - 在导入器消费 KPS 之前执行
    - 缺失引用记录为错误，不阻断导入（降级为 warning 级别）

    Args:
        entities: 已归一化的全部实体列表。
        actions_dir: OWL 包根目录下的 actions/ 子目录。

    Returns:
        错误信息列表，空列表表示全部通过校验。
    """
    errors: list[str] = []

    # 收集 actions/ 目录下所有可用的 Action 文件编码（去掉 .owl 后缀）
    available_actions: set[str] = set()
    if actions_dir.is_dir():
        for f in actions_dir.rglob("*.owl"):
            if f.is_file():
                available_actions.add(f.stem)

    if not available_actions:
        # 无 Action 目录或无文件 → 不做校验（OWL 包可以不包含 Action）
        return []

    # 遍历所有 object/view 类型的定义实体，检查 action_refs
    for entity in entities:
        entity_type = str(entity.get("entity_type", "")).strip()
        if entity_type not in ("object", "view"):
            continue

        action_refs_raw = entity.get("action_refs")
        if not action_refs_raw:
            continue

        # 解析 action_refs（支持 JSON 字符串与已解析的列表两种格式）
        if isinstance(action_refs_raw, str):
            try:
                action_refs = json.loads(action_refs_raw)
            except (json.JSONDecodeError, TypeError):
                entity_code = entity.get("term_code", entity.get("object_code", "unknown"))
                errors.append(
                    f"action_refs JSON 解析失败: entity={entity_code}, "
                    f"value={str(action_refs_raw)[:100]}"
                )
                continue
        elif isinstance(action_refs_raw, list):
            action_refs = action_refs_raw
        else:
            continue

        if not isinstance(action_refs, list):
            continue

        # 逐条校验每个引用的 action_code
        entity_code = entity.get(
            "term_code",
            entity.get("object_code", entity.get("view_code", "unknown")),
        )
        for ref in action_refs:
            ref_code = str(ref).strip()
            if not ref_code:
                continue
            ref_code = ref_code.replace(".owl", "")  # 去掉可能的 .owl 后缀
            if ref_code not in available_actions:
                errors.append(
                    f"action_refs 引用缺失: entity={entity_code}, "
                    f"action={ref_code}（未在 actions/ 目录中找到 {ref_code}.owl 文件）"
                )

    if errors:
        logger.warning("action_refs 校验发现 %d 个错误", len(errors))
    else:
        logger.info(
            "action_refs 校验通过（%d 个可用 Action）",
            len(available_actions),
        )

    return errors


# ── 关系推断 ─────────────────────────────────────────────────────────────────────


def infer_relations_from_definitions(
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """从已解析的实体中推断缺失的关系。

    推断规则（按计划文档 §2.3.2）：
    1. object 的 EntityField 字段 → 合成 HAS_FIELD 关系
       - 当外部分 OWL 包缺少独立的 _attribute_relations.owl 时启用
    2. view 的 object_codes 字段 → 合成 HAS_OBJECT 关系
       - 当外部 OWL 包缺少独立的 _relations.owl 时启用
    3. view 的 SceneField 字段 → 合成 HAS_FIELD 关系（视图域维度）
       - 与 has field 的 prop 区分，此为 view scope

    推断出的关系标记 _inferred=True，调用方可据此与显式声明的关系去重。

    注意：此函数不读取文件系统，仅从已解析的实体 dict 中提取定义信息。
    调用方需确保传入的 entities 已包含 _definition.owl 的解析结果。

    Args:
        entities: 已归一化的全部实体列表（含 object/view 类型的定义实体）。

    Returns:
        推断出的关系实体列表（entity_type="relation"），可直接合并到 entities。
    """
    inferred: list[dict[str, Any]] = []

    for entity in entities:
        entity_type = str(entity.get("entity_type", "")).strip()

        if entity_type == "object":
            # 规则 1：object 下挂的 EntityField → 合成 HAS_FIELD
            # EntityField 描述该对象拥有的数据字段（如 by_customer 的 customer_name）
            for field in _extract_fields(entity):
                field_code = _field_code(field)
                if not field_code:
                    continue
                inferred.append(
                    _make_relation(
                        source_type="object",
                        source_code=str(entity.get("object_code", entity.get("term_code", ""))),
                        target_type="prop",
                        target_code=field_code,
                        relation_name="拥有属性",
                        relation_category="HAS_FIELD",
                    )
                )

        elif entity_type in ("view", "scene"):
            # "场景" 在本模块中已归一化为 "view"，但保留兼容性
            view_code = str(entity.get("view_code", entity.get("object_code", "")))

            # 规则 2：view 的 object_codes → 合成 HAS_OBJECT
            # SceneDefinition.object_codes 列出该视图包含的对象
            for obj_code in _extract_object_codes(entity):
                inferred.append(
                    _make_relation(
                        source_type="view",
                        source_code=view_code,
                        target_type="object",
                        target_code=obj_code,
                        relation_name="包含",
                        relation_category="HAS_OBJECT",
                    )
                )

            # 规则 3：view 的 SceneField → 合成 HAS_FIELD（视图域维度）
            # SceneField 描述视图层面的展示字段（可能来自不同对象）
            for field in _extract_fields(entity):
                field_code = _field_code(field)
                if not field_code:
                    continue
                inferred.append(
                    _make_relation(
                        source_type="view",
                        source_code=view_code,
                        target_type="prop",
                        target_code=field_code,
                        relation_name="拥有属性",
                        relation_category="HAS_FIELD",
                    )
                )

    logger.info("从定义文件推断 %d 条关系", len(inferred))
    return inferred


def _make_relation(
    source_type: str,
    source_code: str,
    target_type: str,
    target_code: str,
    relation_name: str,
    relation_category: str,
) -> dict[str, Any]:
    """构造一条关系实体 dict。

    字段结构与 owl_parser 产出的 relation 实体保持一致，
    可直接被 owl_converter.convert_relation() 消费。
    """
    return {
        "entity_type": "relation",
        "source_type": source_type,
        "source_code": source_code,
        "target_type": target_type,
        "target_code": target_code,
        "relation_name": relation_name,
        "relation_category": relation_category,
        "relation_type": relation_category,
        "cardinality": "1:N",
        "_inferred": True,  # 标记为推断关系，调用方可据此去重或降级处理
    }


def _extract_fields(entity: dict[str, Any]) -> list[dict[str, Any]]:
    """从定义的实体中提取 fields 数组。

    EntityDefinition 和 SceneDefinition 都可能包含 fields，
    存储子字段/属性信息。

    支持两种格式：
    - 已解析的 list[dict]
    - JSON 字符串（可能是历史遗留或 SAX 解析产物）
    """
    fields = entity.get("fields")
    if isinstance(fields, list):
        return [f for f in fields if isinstance(f, dict)]
    if isinstance(fields, str):
        try:
            parsed = json.loads(fields)
            if isinstance(parsed, list):
                return [f for f in parsed if isinstance(f, dict)]
        except (json.JSONDecodeError, TypeError):
            pass
    return []


def _field_code(field: dict[str, Any]) -> str:
    """从 field dict 中提取字段编码。

    fieldCode 是标准字段名，property_code / field_code 为兼容字段。
    """
    return str(
        field.get("fieldCode") or field.get("property_code") or field.get("field_code") or ""
    ).strip()


def _extract_object_codes(entity: dict[str, Any]) -> list[str]:
    """从 SceneDefinition 实体中提取 object_codes 列表。

    SceneDefinition 的 object_codes 声明该视图包含哪些底层对象。

    支持三种格式：
    - 已解析的 list[str]: ["by_customer", "by_project"]
    - JSON 字符串: '["by_customer","by_project"]'
    - 逗号分隔字符串: "by_customer,by_project"
    """
    raw = entity.get("object_codes") or entity.get("objectCodes") or ""
    if not raw:
        return []

    if isinstance(raw, list):
        return [str(c).strip() for c in raw if str(c).strip()]

    if isinstance(raw, str):
        stripped = raw.strip()
        if stripped.startswith("["):
            # JSON 数组格式
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, list):
                    return [str(c).strip() for c in parsed if str(c).strip()]
            except (json.JSONDecodeError, TypeError):
                return []
        else:
            # 逗号分隔格式
            return [c.strip() for c in stripped.split(",") if c.strip()]

    return []


# ── 全流程推断入口 ────────────────────────────────────────────────────────────────


def apply_inference(
    package_dir: Path,
    entities: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """一次调用完成所有推断与校验。

    处理顺序（按计划文档 §2.3.2 的目标数据流）：
    1. 对全部实体执行格式归一化（source_type、joinkeys、term_code_path）
    2. 从 EntityDefinition/SceneDefinition 推断缺失的关系
    3. 校验 action_refs 引用完整性

    此函数是推断层的主入口，可在 executor.run() 或 validate.check_package()
    中调用，确保所有实体在进入转换器之前已完成归一化。

    Args:
        package_dir: OWL 包根目录（用于定位 actions/ 目录）。
        entities: 从 owl_parser 解析出的全部实体列表（所有 OWL 文件）。

    Returns:
        (normalized_entities, errors):
          - normalized_entities: 归一化后的实体列表（含推断出的关系实体）
          - errors: action_refs 校验错误列表（空列表表示全部通过）
    """
    # Step 1: 格式归一化 — 中文类型→英文、joinkeys 字段名标准化、path 小写化
    normalized = normalize_entities(entities)
    logger.info("推断层 Step 1 完成：格式归一化 %d 个实体", len(normalized))

    # Step 2: 关系推断 — 从定义文件的 fields/object_codes 推断缺失关系
    inferred_relations = infer_relations_from_definitions(normalized)
    if inferred_relations:
        normalized.extend(inferred_relations)
        logger.info("推断层 Step 2 完成：追加 %d 条推断关系", len(inferred_relations))

    # Step 3: Action 引用校验 — 验证 action_refs ↔ actions/ 目录一致性
    action_errors = validate_action_refs(normalized, package_dir / "actions")

    if action_errors:
        logger.warning("推断层 Step 3 完成：action_refs 校验发现 %d 个错误", len(action_errors))
    else:
        logger.info("推断层 Step 3 完成：action_refs 校验通过")

    return normalized, action_errors


__all__ = [
    "apply_inference",
    "infer_relations_from_definitions",
    "normalize_entities",
    "normalize_entity",
    "normalize_joinkeys",
    "normalize_source_type",
    "normalize_term_code_path",
    "validate_action_refs",
]
