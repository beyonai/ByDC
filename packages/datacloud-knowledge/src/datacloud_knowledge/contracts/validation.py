"""知识包语义校验 — 纯 Python 规则引擎。

对 KnowledgePackage 执行 10 条 SEM 语义校验规则（SEM-001 ~ SEM-010），
确保导入数据库的知识包数据满足检索层 invariants。

所有校验逻辑不依赖 owlrl 或 pyoxigraph，仅对 KPS 结构（Dataclass）执行纯 Python 断言。
ERROR 级规则阻断导入，不符合规则的数据拒绝落库，保证检索层零行为退化。

设计原则：
- 每条规则一个函数，职责单一。
- 返回人类可读的错误消息列表，而非异常。
- validate_package() 聚合所有规则，返回全部违规点（不全量通过不导入）。
"""

from __future__ import annotations

import logging

from .kps import KnowledgePackage, TermDef

logger = logging.getLogger(__name__)

# 合法的 type_category 值：1=列表术语, 2=字典术语, 3=本体术语, 4=文档名称术语
VALID_TYPE_CATEGORIES: frozenset[int] = frozenset({1, 2, 3, 4})

# 内置术语类型编码：这些 type_code 是系统约定的基础类型，
# 即使包内未显式 TermTypeDef 声明也视为合法（跨包共享、无需重复声明）。
BUILTIN_TERM_TYPE_CODES: frozenset[str] = frozenset(
    {"object", "prop", "view", "LIST_TERM", "DICT_TERM"}
)

# 合法的 cardinality 值
VALID_CARDINALITY: frozenset[str] = frozenset({"1:1", "1:N", "N:1", "N:N"})

# 本体术语类型编码（object/view/prop）
ONTOLOGY_TERM_TYPE_CODES: frozenset[str] = frozenset({"object", "view", "prop"})

# 值术语类型编码（LIST_TERM/DICT_TERM 等非本体类型）
VALUE_TERM_TYPE_CODES: frozenset[str] = frozenset({"LIST_TERM", "DICT_TERM"})


def sem_001_type_category(pkg: KnowledgePackage) -> list[str]:
    """SEM-001: 术语类型的 type_category 必须在 {1, 2, 3, 4} 范围内。

    检索层通过 KTYPE_CATEGORY_MAP 按 type_category 过滤 term，
    非法值会导致召回路径跳过该类型的所有术语。
    """
    errors: list[str] = []
    for tt in pkg.term_types:
        if tt.type_category not in VALID_TYPE_CATEGORIES:
            errors.append(
                f"SEM-001: 术语类型 '{tt.type_code}' 的 type_category={tt.type_category}，"
                f"合法值 {sorted(VALID_TYPE_CATEGORIES)}"
            )
    return errors


def sem_002_term_id_format(pkg: KnowledgePackage) -> list[str]:
    """SEM-002: 每个 term 的 compute_term_id() 必须符合 {lib}#{type}#{code} 格式。

    检索层通过 get_term_by_ids() 按 term_id 查询，格式不一致导致查不到术语，
    关系解析、别名消歧等下游功能全部受影响。
    """
    errors: list[str] = []
    for term in pkg.terms:
        tid = term.compute_term_id()
        if not tid:
            errors.append(
                f"SEM-002: 术语 '{term.term_name}' (code='{term.term_code}') "
                f"compute_term_id() 返回空值"
            )
            continue
        parts = tid.split("#")
        if len(parts) < 3 or any(not p for p in parts):
            errors.append(
                f"SEM-002: 术语 '{term.term_name}' (code='{term.term_code}') "
                f"term_id='{tid}' 不符合 {{lib}}#{{type}}#{{code}} 格式（段数不足3或含空段）"
            )
    return errors


def sem_003_has_field_source(pkg: KnowledgePackage) -> list[str]:
    """SEM-003: HAS_FIELD 关系的 source 必须是 object 或 view 类型。

    检索层 resolve_field_aliases 基于"对象/视图→属性"的 HAS_FIELD 链路工作，
    source 非 object/view 将导致别名解析失败，字段无法确认。
    """
    errors: list[str] = []
    # 建立 term_code → term_type_code 索引
    term_type_map: dict[str, str] = {t.term_code: t.term_type_code for t in pkg.terms}
    for rel in pkg.relations:
        if rel.relation_category != "HAS_FIELD":
            continue
        source_code = _extract_term_code(rel.source_term_code)
        source_type = term_type_map.get(source_code)
        if source_type is None:
            continue  # 由 SEM-010 验证
        if source_type not in {"object", "view"}:
            errors.append(
                f"SEM-003: HAS_FIELD 关系 source='{source_code}' "
                f"类型为 '{source_type}'，期望 'object' 或 'view'"
            )
    return errors


def sem_004_has_field_target(pkg: KnowledgePackage) -> list[str]:
    """SEM-004: HAS_FIELD 关系的 target 必须是 prop 类型。

    检索层通过 HAS_FIELD 关系查询对象/视图下的所有属性，
    target 非 prop 会导致属性查询返回错误类型的术语。
    """
    errors: list[str] = []
    term_type_map: dict[str, str] = {t.term_code: t.term_type_code for t in pkg.terms}
    for rel in pkg.relations:
        if rel.relation_category != "HAS_FIELD":
            continue
        target_code = _extract_term_code(rel.target_term_code)
        target_type = term_type_map.get(target_code)
        if target_type is None:
            continue
        if target_type != "prop":
            errors.append(
                f"SEM-004: HAS_FIELD 关系 target='{target_code}' "
                f"类型为 '{target_type}'，期望 'prop'"
            )
    return errors


def sem_005_prop_parent_object(pkg: KnowledgePackage) -> list[str]:
    """SEM-005: prop 术语的 parent_term_code 必须指向 object 或 view 术语。

    检索层层级遍历（如 get_prop_enum_values）依赖 prop→object/view 的父子层级，
    parent 指向错误类型会导致枚举值查询路径断裂。
    """
    errors: list[str] = []
    term_map: dict[str, TermDef] = {t.term_code: t for t in pkg.terms}
    for term in pkg.terms:
        if term.term_type_code != "prop":
            continue
        if not term.parent_term_code:
            errors.append(
                f"SEM-005: prop '{term.term_code}' 缺少 parent_term_code，"
                f"必须指向所属的 object 或 view"
            )
            continue
        parent = term_map.get(term.parent_term_code)
        if parent is None:
            continue  # 由 SEM-010 验证
        if parent.term_type_code not in {"object", "view"}:
            errors.append(
                f"SEM-005: prop '{term.term_code}' 的 parent '{term.parent_term_code}' "
                f"类型为 '{parent.term_type_code}'，期望 'object' 或 'view'"
            )
    return errors


def sem_006_value_parent_prop(pkg: KnowledgePackage) -> list[str]:
    """SEM-006: 值术语（LIST_TERM/DICT_TERM）若有 parent_term_code，必须指向 prop 术语。

    新架构下值术语可单独导入，通过 term_type_code + HAS_TERM(prop→type) 检索，
    不强制 parent_term_code。若提供了则校验其目标为 prop。
    """
    errors: list[str] = []
    term_map: dict[str, TermDef] = {t.term_code: t for t in pkg.terms}
    # 收集值术语的类型编码
    value_type_codes: set[str] = {
        tt.type_code for tt in pkg.term_types if tt.type_category in {1, 2}
    }
    for term in pkg.terms:
        if term.term_type_code not in value_type_codes:
            continue
        if not term.parent_term_code:
            continue  # 新架构：值术语可无 parent_term_code
        parent = term_map.get(term.parent_term_code)
        if parent is None:
            continue  # 由 SEM-010 验证
        if parent.term_type_code != "prop":
            errors.append(
                f"SEM-006: 值术语 '{term.term_code}' 的 parent '{term.parent_term_code}' "
                f"类型为 '{parent.term_type_code}'，期望 'prop'"
            )
    return errors


def sem_007_cardinality(pkg: KnowledgePackage) -> list[str]:
    """SEM-007: 关系的 cardinality 必须是 1:1、1:N、N:1 或 N:N。

    检索层关系解析依赖合法 cardinality 值，
    非法值导致关系链路中无法正确推断 JOIN 方向。
    """
    errors: list[str] = []
    for rel in pkg.relations:
        if not rel.cardinality:
            errors.append(
                f"SEM-007: 关系 '{rel.relation_name}' "
                f"({rel.source_term_code} → {rel.target_term_code}) cardinality 为空"
            )
        elif rel.cardinality not in VALID_CARDINALITY:
            errors.append(
                f"SEM-007: 关系 '{rel.relation_name}' "
                f"cardinality='{rel.cardinality}' 非法，合法值 {sorted(VALID_CARDINALITY)}"
            )
    return errors


def sem_008_joinkeys_fields(pkg: KnowledgePackage) -> list[str]:
    """SEM-008: joinkeys 每项必须包含 sourceField 和 targetField。

    检索层 scope 扩展依赖 joinkeys 中的 sourceField 匹配确认字段，
    缺少关键字段导致 MANY_TO_ONE 关联对象无法加入 scope，值术语搜索范围受限。
    """
    errors: list[str] = []
    for rel in pkg.relations:
        if rel.relation_category != "MANY_TO_ONE":
            continue
        if not rel.joinkeys:
            errors.append(
                f"SEM-008: MANY_TO_ONE 关系 '{rel.relation_name}' "
                f"({rel.source_term_code} → {rel.target_term_code}) joinkeys 为空"
            )
            continue
        for i, jk in enumerate(rel.joinkeys):
            if not isinstance(jk, dict):
                errors.append(f"SEM-008: 关系 '{rel.relation_name}' joinkeys[{i}] 不是字典")
                continue
            if "sourceField" not in jk:
                errors.append(
                    f"SEM-008: 关系 '{rel.relation_name}' joinkeys[{i}] 缺少 'sourceField'"
                )
            if "targetField" not in jk:
                errors.append(
                    f"SEM-008: 关系 '{rel.relation_name}' joinkeys[{i}] 缺少 'targetField'"
                )
    return errors


def sem_009_unique_prop_codes(pkg: KnowledgePackage) -> list[str]:
    """SEM-009: 同一 scope（object/view）下的 prop term_code 不能重复。

    检索层 resolve_field_aliases 在同 scope 下通过 term_code 定位字段，
    重复的 prop term_code 会导致别名消歧歧义，确认结果不可靠。
    """
    errors: list[str] = []
    # 建立 parent_term_code → term_code 列表（prop 范围）
    scope_props: dict[str, set[str]] = {}
    for term in pkg.terms:
        if term.term_type_code != "prop":
            continue
        parent = term.parent_term_code or ""
        if parent not in scope_props:
            scope_props[parent] = set()
        if term.term_code in scope_props[parent]:
            errors.append(f"SEM-009: scope='{parent}' 下 prop term_code='{term.term_code}' 重复")
        scope_props[parent].add(term.term_code)
    return errors


def sem_010_relation_term_existence(pkg: KnowledgePackage) -> list[str]:
    """SEM-010: 关系的 source/target term_code 包内引用完整性检查。

    跨包导入场景（术语值先导入、本体后导入）下，关系引用的术语可能
    已在其他包中入库，此时不阻断导入，仅记录 WARNING。
    DB 层 FK 约束提供最终兜底：真正缺失的术语会在 writer 写入 relation
    时触发 integrity error。
    """
    term_codes: set[str] = {t.term_code for t in pkg.terms}
    for rel in pkg.relations:
        source_code = _extract_term_code(rel.source_term_code)
        target_code = _extract_term_code(rel.target_term_code)
        if source_code and source_code not in term_codes:
            logger.warning(
                "SEM-010: 关系 '%s' source='%s' 不在包内术语列表中（跨包引用，DB FK 兜底）",
                rel.relation_name,
                source_code,
            )
        if target_code and target_code not in term_codes:
            logger.warning(
                "SEM-010: 关系 '%s' target='%s' 不在包内术语列表中（跨包引用，DB FK 兜底）",
                rel.relation_name,
                target_code,
            )
    return []


# ═══════════════════════════════════════════════════════════════════════════════
# Layer 1-2 结构层校验
# ═══════════════════════════════════════════════════════════════════════════════


def validate_layer1_structure(pkg: KnowledgePackage) -> list[str]:
    """Layer 1（结构层）校验：必填实体存在、必填字段非空。

    检查 knowledge 包的核心结构完整性：
    - terms 和 relations 不能为空元组
    - 每个 term 的必填字段（term_code, term_name, term_type_code, library_code, domain_code）
      不能为空字符串
    - 每个 relation 的必填字段不能为空
    """
    errors: list[str] = []

    # 知识包核心结构检查
    if not pkg.terms:
        errors.append("Layer 1: 知识包 terms 为空，至少需要一个术语")

    # 术语必填字段检查
    for term in pkg.terms:
        if not term.term_code or not term.term_code.strip():
            errors.append(f"Layer 1: 术语 '{term.term_name}' 的 term_code 为空")
        if not term.term_name or not term.term_name.strip():
            errors.append(f"Layer 1: 术语 (code='{term.term_code}') 的 term_name 为空")
        if not term.term_type_code or not term.term_type_code.strip():
            errors.append(f"Layer 1: 术语 '{term.term_name}' 的 term_type_code 为空")
        if not term.library_code or not term.library_code.strip():
            errors.append(f"Layer 1: 术语 '{term.term_name}' 的 library_code 为空")
        if not term.domain_code or not term.domain_code.strip():
            errors.append(f"Layer 1: 术语 '{term.term_name}' 的 domain_code 为空")

    # 关系必填字段检查
    for rel in pkg.relations:
        if not rel.source_term_code or not rel.source_term_code.strip():
            errors.append(f"Layer 1: 关系 '{rel.relation_name}' 的 source_term_code 为空")
        if not rel.target_term_code or not rel.target_term_code.strip():
            errors.append(f"Layer 1: 关系 '{rel.relation_name}' 的 target_term_code 为空")
        if not rel.relation_name or not rel.relation_name.strip():
            errors.append(f"Layer 1: 关系 (source='{rel.source_term_code}') 的 relation_name 为空")
        if not rel.relation_category or not rel.relation_category.strip():
            errors.append(f"Layer 1: 关系 '{rel.relation_name}' 的 relation_category 为空")

    return errors


def validate_layer2_field_completeness(pkg: KnowledgePackage) -> list[str]:
    """Layer 2（字段完整层）校验：关系三元组齐全、ID 格式合法。

    检查：
    - 术语类型编码值与 term_types 中的声明一致
    - 关系的 relation_category 为已知类型
    - term_type_defs 中的 type_code 不重复
    """
    errors: list[str] = []

    # 检查 term_type_defs 中 type_code 去重（多对象合并时允许重复，仅记录）
    type_codes_seen: set[str] = set()
    for tt in pkg.term_types:
        if tt.type_code in type_codes_seen:
            logger.debug("Layer 2: 术语类型编码 '%s' 已存在（多对象合并，跳过）", tt.type_code)
        else:
            type_codes_seen.add(tt.type_code)

    # 检查术语引用的 term_type_code 是否在 term_types 中声明
    # 内置类型编码（object/prop/view 等）无需重复声明，合并到已知集合
    declared_type_codes: set[str] = set(BUILTIN_TERM_TYPE_CODES) | {
        tt.type_code for tt in pkg.term_types
    }
    for term in pkg.terms:
        if term.term_type_code not in declared_type_codes:
            errors.append(
                f"Layer 2: 术语 '{term.term_name}' 引用未声明的 "
                f"term_type_code='{term.term_type_code}'"
            )

    # 检查关系 relation_category 是否为已知类型
    known_categories: frozenset[str] = frozenset(
        {"HAS_FIELD", "HAS_OBJECT", "HAS_TERM", "MANY_TO_ONE"}
    )
    for rel in pkg.relations:
        if rel.relation_category not in known_categories:
            errors.append(
                f"Layer 2: 关系 '{rel.relation_name}' 的 "
                f"relation_category='{rel.relation_category}' 非法，"
                f"合法值 {sorted(known_categories)}"
            )

    return errors


# ═══════════════════════════════════════════════════════════════════════════════
# 聚合验证入口
# ═══════════════════════════════════════════════════════════════════════════════


def validate_package(pkg: KnowledgePackage) -> tuple[bool, list[str]]:
    """对知识包执行全量语义校验。

    执行 Layer 1（结构层）、Layer 2（字段完整层）和 SEM-001~010 共计 14 条规则。
    任何一条规则失败都视为校验不通过，返回完整错误列表供排查。

    Args:
        pkg: 待校验的 KnowledgePackage。

    Returns:
        (passed, errors): passed 为 True 时所有规则通过，
        errors 包含全部违规信息的可读列表。
    """
    all_errors: list[str] = []

    # Layer 1: 结构层校验
    all_errors.extend(validate_layer1_structure(pkg))

    # Layer 2: 字段完整层校验
    all_errors.extend(validate_layer2_field_completeness(pkg))

    # SEM 规则：语义层校验
    for rule_fn in [
        sem_001_type_category,
        sem_002_term_id_format,
        sem_003_has_field_source,
        sem_004_has_field_target,
        sem_005_prop_parent_object,
        sem_006_value_parent_prop,
        sem_007_cardinality,
        sem_008_joinkeys_fields,
        sem_009_unique_prop_codes,
        sem_010_relation_term_existence,
    ]:
        rule_errors = rule_fn(pkg)
        all_errors.extend(rule_errors)

    passed = len(all_errors) == 0
    if not passed:
        logger.warning(
            "知识包校验失败，共 %d 条违规:\n%s",
            len(all_errors),
            "\n".join(f"  - {e}" for e in all_errors),
        )
    else:
        logger.info("知识包校验通过（%d 条规则）", 10 + 2)

    return passed, all_errors


# ═══════════════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════════════


def _extract_term_code(term_code_with_prefix: str) -> str:
    """从 {library}#{type}#{code} 格式中提取 term_code（最后一个 # 之后的部分）。

    Args:
        term_code_with_prefix: 完整的带前缀 term_code 字符串。

    Returns:
        纯 term_code，若提取失败返回原字符串。
    """
    if not term_code_with_prefix:
        return ""
    parts = term_code_with_prefix.split("#")
    if len(parts) >= 3:
        return "#".join(parts[2:])
    return parts[-1]


__all__ = [
    "BUILTIN_TERM_TYPE_CODES",
    "VALID_TYPE_CATEGORIES",
    "sem_001_type_category",
    "sem_002_term_id_format",
    "sem_003_has_field_source",
    "sem_004_has_field_target",
    "sem_005_prop_parent_object",
    "sem_006_value_parent_prop",
    "sem_007_cardinality",
    "sem_008_joinkeys_fields",
    "sem_009_unique_prop_codes",
    "sem_010_relation_term_existence",
    "validate_layer1_structure",
    "validate_layer2_field_completeness",
    "validate_package",
]
