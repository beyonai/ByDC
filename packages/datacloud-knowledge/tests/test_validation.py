"""知识包校验规则单元测试 — SEM-001 ~ SEM-010 + Layer 1/2 结构校验。

测试 validate_package() 及各独立规则函数对合法/非法知识包的判定。
"""

from __future__ import annotations

from datacloud_knowledge.contracts.kps import (
    KnowledgePackage,
    RelationDef,
    TermDef,
    TermTypeDef,
)
from datacloud_knowledge.contracts.validation import (
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
    validate_layer1_structure,
    validate_layer2_field_completeness,
    validate_package,
)

# ═══════════════════════════════════════════════════════════════════════════════
# 测试辅助
# ═══════════════════════════════════════════════════════════════════════════════


def _make_valid_pkg() -> KnowledgePackage:
    """构造一个最小合法 KnowledgePackage，各测试以此为基准修改。"""
    return KnowledgePackage(
        terms=(
            TermDef(
                term_code="by_customer",
                term_name="客户",
                term_type_code="object",
                library_code="L1",
                domain_code="D1",
            ),
            TermDef(
                term_code="customer_name",
                term_name="客户名称",
                term_type_code="prop",
                library_code="L1",
                domain_code="D1",
                parent_term_code="by_customer",
            ),
        ),
        relations=(
            RelationDef(
                source_term_code="L1#object#by_customer",
                target_term_code="L1#prop#customer_name",
                relation_name="客户_拥有字段_客户名称",
                relation_category="HAS_FIELD",
                cardinality="1:N",
                ext_field={"field_alias": "客户名称"},
            ),
        ),
        term_types=(
            TermTypeDef(type_code="object", type_name="对象", type_category=3),
            TermTypeDef(type_code="prop", type_name="属性", type_category=3),
        ),
    )


def _make_full_pkg() -> KnowledgePackage:
    """构造一个含值术语 + MANY_TO_ONE 关系的完整合法 KnowledgePackage。"""
    return KnowledgePackage(
        terms=(
            TermDef(
                term_code="by_customer",
                term_name="客户",
                term_type_code="object",
                library_code="L1",
                domain_code="D1",
            ),
            TermDef(
                term_code="by_project",
                term_name="项目",
                term_type_code="object",
                library_code="L1",
                domain_code="D1",
            ),
            TermDef(
                term_code="customer_name",
                term_name="客户名称",
                term_type_code="prop",
                library_code="L1",
                domain_code="D1",
                parent_term_code="by_customer",
            ),
            TermDef(
                term_code="opp_stage",
                term_name="商机阶段",
                term_type_code="prop",
                library_code="L1",
                domain_code="D1",
                parent_term_code="by_customer",
            ),
            TermDef(
                term_code="STAGE_NEGO",
                term_name="谈判阶段",
                term_type_code="LIST_TERM",
                library_code="L1",
                domain_code="D1",
                parent_term_code="opp_stage",
            ),
        ),
        relations=(
            RelationDef(
                source_term_code="L1#object#by_customer",
                target_term_code="L1#prop#customer_name",
                relation_name="客户_拥有字段_客户名称",
                relation_category="HAS_FIELD",
                cardinality="1:N",
                ext_field={"field_alias": "客户名称"},
            ),
            RelationDef(
                source_term_code="L1#object#by_customer",
                target_term_code="L1#prop#opp_stage",
                relation_name="客户_拥有字段_商机阶段",
                relation_category="HAS_FIELD",
                cardinality="1:N",
                ext_field={"field_alias": "商机阶段"},
            ),
            RelationDef(
                source_term_code="L1#object#by_customer",
                target_term_code="L1#object#by_project",
                relation_name="客户_关联_项目",
                relation_category="MANY_TO_ONE",
                cardinality="N:1",
                joinkeys=({"sourceField": "project_id", "targetField": "id"},),
            ),
        ),
        term_types=(
            TermTypeDef(type_code="object", type_name="对象", type_category=3),
            TermTypeDef(type_code="prop", type_name="属性", type_category=3),
            TermTypeDef(type_code="LIST_TERM", type_name="列表术语", type_category=1),
            TermTypeDef(type_code="DICT_TERM", type_name="字典术语", type_category=2),
        ),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# validate_package 全量校验 — 合法包
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidatePackageValid:
    """valid KnowledgePackage 通过全量校验。"""

    def test_valid_minimal_package(self) -> None:
        """最小合法包通过校验。"""
        passed, errors = validate_package(_make_valid_pkg())
        assert passed, f"Unexpected errors: {errors}"
        assert len(errors) == 0

    def test_valid_full_package(self) -> None:
        """完整包（含值术语 + MANY_TO_ONE）通过校验。"""
        passed, errors = validate_package(_make_full_pkg())
        assert passed, f"Unexpected errors: {errors}"
        assert len(errors) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# SEM-001: illegal type_category
# ═══════════════════════════════════════════════════════════════════════════════


class TestSem001:
    """SEM-001: type_category 必须 ∈ {1, 2, 3, 4}。"""

    def test_invalid_category_0(self) -> None:
        """type_category=0 触发 SEM-001。"""
        pkg = KnowledgePackage(
            terms=(
                TermDef(
                    term_code="obj",
                    term_name="对象",
                    term_type_code="object",
                    library_code="L1",
                    domain_code="D1",
                ),
            ),
            relations=(),
            term_types=(TermTypeDef(type_code="object", type_name="对象", type_category=0),),
        )
        errors = sem_001_type_category(pkg)
        assert any("SEM-001" in e for e in errors)

    def test_invalid_category_99(self) -> None:
        """type_category=99 触发 SEM-001。"""
        pkg = KnowledgePackage(
            terms=(),
            relations=(),
            term_types=(TermTypeDef(type_code="bad", type_name="非法", type_category=99),),
        )
        errors = sem_001_type_category(pkg)
        assert any("SEM-001" in e and "99" in e for e in errors)

    def test_valid_categories_pass(self) -> None:
        """合法 category 值 1-4 全部通过。"""
        pkg = KnowledgePackage(
            terms=(
                TermDef(
                    term_code="obj",
                    term_name="对象",
                    term_type_code="object",
                    library_code="L1",
                    domain_code="D1",
                ),
            ),
            relations=(),
            term_types=(
                TermTypeDef(type_code="L", type_name="list", type_category=1),
                TermTypeDef(type_code="D", type_name="dict", type_category=2),
                TermTypeDef(type_code="O", type_name="onto", type_category=3),
                TermTypeDef(type_code="DN", type_name="doc_name", type_category=4),
            ),
        )
        errors = sem_001_type_category(pkg)
        assert len(errors) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# SEM-002: empty / malformed term_id
# ═══════════════════════════════════════════════════════════════════════════════


class TestSem002:
    """SEM-002: term_id 必须符合 {lib}#{type}#{code} 格式。"""

    def test_valid_term_id(self) -> None:
        """合法 term_id 不触发 SEM-002。"""
        pkg = _make_valid_pkg()
        errors = sem_002_term_id_format(pkg)
        assert len(errors) == 0

    def test_empty_term_code_triggers_error(self) -> None:
        """term_code 空字符串导致 term_id 段数不足。"""
        pkg = KnowledgePackage(
            terms=(
                TermDef(
                    term_code="",
                    term_name="空编码",
                    term_type_code="object",
                    library_code="L1",
                    domain_code="D1",
                ),
            ),
            relations=(),
        )
        errors = sem_002_term_id_format(pkg)
        assert any("含空段" in e for e in errors), f"Got: {errors}"


# ═══════════════════════════════════════════════════════════════════════════════
# SEM-003 / SEM-004: HAS_FIELD source/target type
# ═══════════════════════════════════════════════════════════════════════════════


class TestSem003:
    """SEM-003: HAS_FIELD source 必须为 object 或 view。"""

    def test_source_is_view_passes(self) -> None:
        """source=view 通过。"""
        pkg = KnowledgePackage(
            terms=(
                TermDef(
                    term_code="scene_sales",
                    term_name="销售视图",
                    term_type_code="view",
                    library_code="L1",
                    domain_code="D1",
                ),
                TermDef(
                    term_code="prop_x",
                    term_name="属性X",
                    term_type_code="prop",
                    library_code="L1",
                    domain_code="D1",
                    parent_term_code="scene_sales",
                ),
            ),
            relations=(
                RelationDef(
                    source_term_code="L1#view#scene_sales",
                    target_term_code="L1#prop#prop_x",
                    relation_name="视图_拥有字段_属性X",
                    relation_category="HAS_FIELD",
                    cardinality="1:N",
                ),
            ),
            term_types=(
                TermTypeDef(type_code="view", type_name="视图", type_category=3),
                TermTypeDef(type_code="prop", type_name="属性", type_category=3),
            ),
        )
        errors = sem_003_has_field_source(pkg)
        assert len(errors) == 0

    def test_source_is_prop_triggers_error(self) -> None:
        """source=prop 触发 SEM-003。"""
        pkg = KnowledgePackage(
            terms=(
                TermDef(
                    term_code="prop_a",
                    term_name="属性A",
                    term_type_code="prop",
                    library_code="L1",
                    domain_code="D1",
                ),
                TermDef(
                    term_code="prop_b",
                    term_name="属性B",
                    term_type_code="prop",
                    library_code="L1",
                    domain_code="D1",
                ),
            ),
            relations=(
                RelationDef(
                    source_term_code="L1#prop#prop_a",
                    target_term_code="L1#prop#prop_b",
                    relation_name="属性A_拥有_属性B",
                    relation_category="HAS_FIELD",
                    cardinality="1:N",
                ),
            ),
            term_types=(TermTypeDef(type_code="prop", type_name="属性", type_category=3),),
        )
        errors = sem_003_has_field_source(pkg)
        assert any("SEM-003" in e for e in errors)


class TestSem004:
    """SEM-004: HAS_FIELD target 必须为 prop。"""

    def test_target_is_object_triggers_error(self) -> None:
        """target=object 触发 SEM-004。"""
        pkg = KnowledgePackage(
            terms=(
                TermDef(
                    term_code="obj_a",
                    term_name="对象A",
                    term_type_code="object",
                    library_code="L1",
                    domain_code="D1",
                ),
                TermDef(
                    term_code="obj_b",
                    term_name="对象B",
                    term_type_code="object",
                    library_code="L1",
                    domain_code="D1",
                ),
            ),
            relations=(
                RelationDef(
                    source_term_code="L1#object#obj_a",
                    target_term_code="L1#object#obj_b",
                    relation_name="对象A_拥有_对象B",
                    relation_category="HAS_FIELD",
                    cardinality="1:N",
                ),
            ),
            term_types=(TermTypeDef(type_code="object", type_name="对象", type_category=3),),
        )
        errors = sem_004_has_field_target(pkg)
        assert any("SEM-004" in e for e in errors)

    def test_target_is_prop_passes(self) -> None:
        """target=prop 通过 SEM-004。"""
        pkg = _make_valid_pkg()
        errors = sem_004_has_field_target(pkg)
        assert len(errors) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# SEM-005: prop missing parent_term_code
# ═══════════════════════════════════════════════════════════════════════════════


class TestSem005:
    """SEM-005: prop 必须有 parent_term_code 指向 object 或 view。"""

    def test_prop_without_parent(self) -> None:
        """prop 无 parent_term_code 触发 SEM-005。"""
        pkg = KnowledgePackage(
            terms=(
                TermDef(
                    term_code="orphan_prop",
                    term_name="孤儿属性",
                    term_type_code="prop",
                    library_code="L1",
                    domain_code="D1",
                ),
            ),
            relations=(),
            term_types=(TermTypeDef(type_code="prop", type_name="属性", type_category=3),),
        )
        errors = sem_005_prop_parent_object(pkg)
        assert any("SEM-005" in e and "缺少 parent_term_code" in e for e in errors)

    def test_prop_parent_not_object_or_view(self) -> None:
        """prop 的 parent 不是 object/view 触发 SEM-005。"""
        pkg = KnowledgePackage(
            terms=(
                TermDef(
                    term_code="parent_prop",
                    term_name="父属性",
                    term_type_code="prop",
                    library_code="L1",
                    domain_code="D1",
                ),
                TermDef(
                    term_code="child_prop",
                    term_name="子属性",
                    term_type_code="prop",
                    library_code="L1",
                    domain_code="D1",
                    parent_term_code="parent_prop",
                ),
            ),
            relations=(),
            term_types=(TermTypeDef(type_code="prop", type_name="属性", type_category=3),),
        )
        errors = sem_005_prop_parent_object(pkg)
        assert any("SEM-005" in e for e in errors)

    def test_prop_parent_object_passes(self) -> None:
        """prop 的 parent 是 object 通过。"""
        pkg = _make_valid_pkg()
        errors = sem_005_prop_parent_object(pkg)
        assert len(errors) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# SEM-006: value term parent must be prop
# ═══════════════════════════════════════════════════════════════════════════════


class TestSem006:
    """SEM-006: 值术语 parent 必须为 prop。"""

    def test_value_term_without_parent(self) -> None:
        """值术语无 parent_term_code 不再触发 SEM-006（新架构允许单独导入）。"""
        pkg = KnowledgePackage(
            terms=(
                TermDef(
                    term_code="VAL_X",
                    term_name="值X",
                    term_type_code="LIST_TERM",
                    library_code="L1",
                    domain_code="D1",
                ),
            ),
            relations=(),
            term_types=(TermTypeDef(type_code="LIST_TERM", type_name="列表术语", type_category=1),),
        )
        errors = sem_006_value_parent_prop(pkg)
        assert len(errors) == 0

    def test_value_term_parent_not_prop(self) -> None:
        """值术语的 parent 不是 prop 触发 SEM-006。"""
        pkg = KnowledgePackage(
            terms=(
                TermDef(
                    term_code="obj_a",
                    term_name="对象A",
                    term_type_code="object",
                    library_code="L1",
                    domain_code="D1",
                ),
                TermDef(
                    term_code="VAL_X",
                    term_name="值X",
                    term_type_code="LIST_TERM",
                    library_code="L1",
                    domain_code="D1",
                    parent_term_code="obj_a",
                ),
            ),
            relations=(),
            term_types=(
                TermTypeDef(type_code="object", type_name="对象", type_category=3),
                TermTypeDef(type_code="LIST_TERM", type_name="列表术语", type_category=1),
            ),
        )
        errors = sem_006_value_parent_prop(pkg)
        assert any("SEM-006" in e for e in errors)

    def test_value_term_parent_prop_passes(self) -> None:
        """值术语 parent=prop 通过 SEM-006。"""
        pkg = _make_full_pkg()
        errors = sem_006_value_parent_prop(pkg)
        assert len(errors) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# SEM-007: invalid cardinality
# ═══════════════════════════════════════════════════════════════════════════════


class TestSem007:
    """SEM-007: cardinality 必须 ∈ {1:1, 1:N, N:1, N:N}。"""

    def test_empty_cardinality(self) -> None:
        """空 cardinality 触发 SEM-007。"""
        pkg = KnowledgePackage(
            terms=(
                TermDef(
                    term_code="obj",
                    term_name="对象",
                    term_type_code="object",
                    library_code="L1",
                    domain_code="D1",
                ),
            ),
            relations=(
                RelationDef(
                    source_term_code="L1#object#obj",
                    target_term_code="L1#object#obj",
                    relation_name="自关联",
                    relation_category="MANY_TO_ONE",
                    cardinality="",
                ),
            ),
        )
        errors = sem_007_cardinality(pkg)
        assert any("cardinality 为空" in e for e in errors)

    def test_invalid_cardinality_value(self) -> None:
        """非法 cardinality 值触发 SEM-007。"""
        pkg = KnowledgePackage(
            terms=(
                TermDef(
                    term_code="obj",
                    term_name="对象",
                    term_type_code="object",
                    library_code="L1",
                    domain_code="D1",
                ),
            ),
            relations=(
                RelationDef(
                    source_term_code="L1#object#obj",
                    target_term_code="L1#object#obj",
                    relation_name="自关联",
                    relation_category="MANY_TO_ONE",
                    cardinality="X:Y",
                ),
            ),
        )
        errors = sem_007_cardinality(pkg)
        assert any("非法" in e for e in errors)

    def test_all_valid_cardinalities(self) -> None:
        """全部合法 cardinality 值通过。"""
        pkg = _make_full_pkg()
        errors = sem_007_cardinality(pkg)
        assert len(errors) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# SEM-008: MANY_TO_ONE missing joinkeys or fields
# ═══════════════════════════════════════════════════════════════════════════════


class TestSem008:
    """SEM-008: MANY_TO_ONE 必须包含 joinkeys 且每项有 sourceField/targetField。"""

    def test_many_to_one_without_joinkeys(self) -> None:
        """MANY_TO_ONE 无 joinkeys 触发 SEM-008。"""
        pkg = KnowledgePackage(
            terms=(
                TermDef(
                    term_code="obj_a",
                    term_name="A",
                    term_type_code="object",
                    library_code="L1",
                    domain_code="D1",
                ),
                TermDef(
                    term_code="obj_b",
                    term_name="B",
                    term_type_code="object",
                    library_code="L1",
                    domain_code="D1",
                ),
            ),
            relations=(
                RelationDef(
                    source_term_code="L1#object#obj_a",
                    target_term_code="L1#object#obj_b",
                    relation_name="A→B",
                    relation_category="MANY_TO_ONE",
                    cardinality="N:1",
                ),
            ),
        )
        errors = sem_008_joinkeys_fields(pkg)
        assert any("SEM-008" in e and "joinkeys 为空" in e for e in errors)

    def test_joinkeys_missing_source_field(self) -> None:
        """joinkeys 缺少 sourceField 触发 SEM-008。"""
        pkg = KnowledgePackage(
            terms=(
                TermDef(
                    term_code="obj_a",
                    term_name="A",
                    term_type_code="object",
                    library_code="L1",
                    domain_code="D1",
                ),
                TermDef(
                    term_code="obj_b",
                    term_name="B",
                    term_type_code="object",
                    library_code="L1",
                    domain_code="D1",
                ),
            ),
            relations=(
                RelationDef(
                    source_term_code="L1#object#obj_a",
                    target_term_code="L1#object#obj_b",
                    relation_name="A→B",
                    relation_category="MANY_TO_ONE",
                    cardinality="N:1",
                    joinkeys=({"targetField": "id"},),
                ),
            ),
        )
        errors = sem_008_joinkeys_fields(pkg)
        assert any("缺少 'sourceField'" in e for e in errors)

    def test_joinkeys_missing_target_field(self) -> None:
        """joinkeys 缺少 targetField 触发 SEM-008。"""
        pkg = KnowledgePackage(
            terms=(
                TermDef(
                    term_code="obj_a",
                    term_name="A",
                    term_type_code="object",
                    library_code="L1",
                    domain_code="D1",
                ),
                TermDef(
                    term_code="obj_b",
                    term_name="B",
                    term_type_code="object",
                    library_code="L1",
                    domain_code="D1",
                ),
            ),
            relations=(
                RelationDef(
                    source_term_code="L1#object#obj_a",
                    target_term_code="L1#object#obj_b",
                    relation_name="A→B",
                    relation_category="MANY_TO_ONE",
                    cardinality="N:1",
                    joinkeys=({"sourceField": "b_id"},),
                ),
            ),
        )
        errors = sem_008_joinkeys_fields(pkg)
        assert any("缺少 'targetField'" in e for e in errors)

    def test_has_field_ignores_joinkey_checks(self) -> None:
        """HAS_FIELD 关系不检查 joinkeys。"""
        pkg = _make_valid_pkg()
        errors = sem_008_joinkeys_fields(pkg)
        assert len(errors) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# SEM-009: duplicate prop term_code
# ═══════════════════════════════════════════════════════════════════════════════


class TestSem009:
    """SEM-009: 同一 scope 下的 prop term_code 不能重复。"""

    def test_duplicate_prop_code_same_parent(self) -> None:
        """同 parent 下重复 prop 触发 SEM-009。"""
        pkg = KnowledgePackage(
            terms=(
                TermDef(
                    term_code="obj",
                    term_name="对象",
                    term_type_code="object",
                    library_code="L1",
                    domain_code="D1",
                ),
                TermDef(
                    term_code="dup_prop",
                    term_name="重复属性1",
                    term_type_code="prop",
                    library_code="L1",
                    domain_code="D1",
                    parent_term_code="obj",
                ),
                TermDef(
                    term_code="dup_prop",
                    term_name="重复属性2",
                    term_type_code="prop",
                    library_code="L1",
                    domain_code="D1",
                    parent_term_code="obj",
                ),
            ),
            relations=(
                RelationDef(
                    source_term_code="L1#object#obj",
                    target_term_code="L1#prop#dup_prop",
                    relation_name="对象_拥有_属性",
                    relation_category="HAS_FIELD",
                    cardinality="1:N",
                ),
            ),
            term_types=(
                TermTypeDef(type_code="object", type_name="对象", type_category=3),
                TermTypeDef(type_code="prop", type_name="属性", type_category=3),
            ),
        )
        errors = sem_009_unique_prop_codes(pkg)
        assert any("SEM-009" in e and "dup_prop" in e for e in errors)

    def test_unique_prop_codes_pass(self) -> None:
        """不同 code 的 prop 在同一个 scope 下通过。"""
        pkg = _make_full_pkg()
        errors = sem_009_unique_prop_codes(pkg)
        assert len(errors) == 0

    def test_same_code_different_parents_passes(self) -> None:
        """不同 parent 下同名 prop 通过。"""
        pkg = KnowledgePackage(
            terms=(
                TermDef(
                    term_code="obj_a",
                    term_name="A",
                    term_type_code="object",
                    library_code="L1",
                    domain_code="D1",
                ),
                TermDef(
                    term_code="obj_b",
                    term_name="B",
                    term_type_code="object",
                    library_code="L1",
                    domain_code="D1",
                ),
                TermDef(
                    term_code="name",
                    term_name="名称A",
                    term_type_code="prop",
                    library_code="L1",
                    domain_code="D1",
                    parent_term_code="obj_a",
                ),
                TermDef(
                    term_code="name",
                    term_name="名称B",
                    term_type_code="prop",
                    library_code="L1",
                    domain_code="D1",
                    parent_term_code="obj_b",
                ),
            ),
            relations=(
                RelationDef(
                    source_term_code="L1#object#obj_a",
                    target_term_code="L1#prop#name",
                    relation_name="A_拥有_名称",
                    relation_category="HAS_FIELD",
                    cardinality="1:N",
                ),
                RelationDef(
                    source_term_code="L1#object#obj_b",
                    target_term_code="L1#prop#name",
                    relation_name="B_拥有_名称",
                    relation_category="HAS_FIELD",
                    cardinality="1:N",
                ),
            ),
            term_types=(
                TermTypeDef(type_code="object", type_name="对象", type_category=3),
                TermTypeDef(type_code="prop", type_name="属性", type_category=3),
            ),
        )
        errors = sem_009_unique_prop_codes(pkg)
        assert len(errors) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# SEM-010: relation references non-existent term
# ═══════════════════════════════════════════════════════════════════════════════


class TestSem010:
    """SEM-010: 跨包引入场景下不阻断，仅 WARNING 日志；DB FK 兜底。"""

    def test_missing_source_term_warns_not_blocks(self) -> None:
        """source term_code 不在包内不返回 error，仅日志 WARNING。"""
        pkg = KnowledgePackage(
            terms=(
                TermDef(
                    term_code="existing",
                    term_name="存在",
                    term_type_code="object",
                    library_code="L1",
                    domain_code="D1",
                ),
            ),
            relations=(
                RelationDef(
                    source_term_code="L1#object#missing",
                    target_term_code="L1#object#existing",
                    relation_name="缺失→存在",
                    relation_category="MANY_TO_ONE",
                    cardinality="N:1",
                ),
            ),
        )
        errors = sem_010_relation_term_existence(pkg)
        assert len(errors) == 0  # 不再阻断，改为 WARNING 日志

    def test_missing_target_term_warns_not_blocks(self) -> None:
        """target term_code 不在包内不返回 error，仅日志 WARNING。"""
        pkg = KnowledgePackage(
            terms=(
                TermDef(
                    term_code="existing",
                    term_name="存在",
                    term_type_code="object",
                    library_code="L1",
                    domain_code="D1",
                ),
            ),
            relations=(
                RelationDef(
                    source_term_code="L1#object#existing",
                    target_term_code="L1#object#missing",
                    relation_name="存在→缺失",
                    relation_category="MANY_TO_ONE",
                    cardinality="N:1",
                ),
            ),
        )
        errors = sem_010_relation_term_existence(pkg)
        assert len(errors) == 0  # 不再阻断，改为 WARNING 日志

    def test_all_terms_exist_passes(self) -> None:
        """所有引用的术语都存在时通过。"""
        pkg = _make_full_pkg()
        errors = sem_010_relation_term_existence(pkg)
        assert len(errors) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Layer 1: 结构层校验
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidateLayer1:
    """validate_layer1_structure 校验。"""

    def test_empty_terms(self) -> None:
        """空 terms 触发 Layer 1 错误。"""
        pkg = KnowledgePackage(
            terms=(),
            relations=(
                RelationDef(
                    source_term_code="L1#object#x",
                    target_term_code="L1#object#x",
                    relation_name="x",
                    relation_category="MANY_TO_ONE",
                    cardinality="N:1",
                ),
            ),
        )
        errors = validate_layer1_structure(pkg)
        assert any("terms 为空" in e for e in errors)

    def test_empty_relations(self) -> None:
        """空 relations 不再触发 Layer 1 错误（术语值单独导入无需关系）。"""
        pkg = KnowledgePackage(
            terms=(
                TermDef(
                    term_code="x",
                    term_name="X",
                    term_type_code="object",
                    library_code="L1",
                    domain_code="D1",
                ),
            ),
            relations=(),
        )
        errors = validate_layer1_structure(pkg)
        assert not any("relations 为空" in e for e in errors)

    def test_missing_required_field_term_name(self) -> None:
        """term_name 为空触发 Layer 1 错误。"""
        pkg = KnowledgePackage(
            terms=(
                TermDef(
                    term_code="test",
                    term_name="",
                    term_type_code="object",
                    library_code="L1",
                    domain_code="D1",
                ),
            ),
            relations=(
                RelationDef(
                    source_term_code="L1#object#test",
                    target_term_code="L1#object#test",
                    relation_name="test",
                    relation_category="MANY_TO_ONE",
                    cardinality="N:1",
                ),
            ),
        )
        errors = validate_layer1_structure(pkg)
        assert any("term_name 为空" in e for e in errors)

    def test_missing_relation_category(self) -> None:
        """relation_category 为空触发 Layer 1 错误。"""
        pkg = KnowledgePackage(
            terms=(
                TermDef(
                    term_code="x",
                    term_name="X",
                    term_type_code="object",
                    library_code="L1",
                    domain_code="D1",
                ),
            ),
            relations=(
                RelationDef(
                    source_term_code="L1#object#x",
                    target_term_code="L1#object#x",
                    relation_name="x",
                    relation_category="",
                    cardinality="N:1",
                ),
            ),
        )
        errors = validate_layer1_structure(pkg)
        assert any("relation_category 为空" in e for e in errors)

    def test_missing_source_term_code(self) -> None:
        """source_term_code 为空触发 Layer 1 错误。"""
        pkg = KnowledgePackage(
            terms=(
                TermDef(
                    term_code="x",
                    term_name="X",
                    term_type_code="object",
                    library_code="L1",
                    domain_code="D1",
                ),
            ),
            relations=(
                RelationDef(
                    source_term_code="",
                    target_term_code="L1#object#x",
                    relation_name="x",
                    relation_category="MANY_TO_ONE",
                    cardinality="N:1",
                ),
            ),
        )
        errors = validate_layer1_structure(pkg)
        assert any("source_term_code 为空" in e for e in errors)

    def test_valid_package_passes(self) -> None:
        """合法结构包通过 Layer 1。"""
        pkg = _make_valid_pkg()
        errors = validate_layer1_structure(pkg)
        assert len(errors) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Layer 2: 字段完整层校验
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidateLayer2:
    """validate_layer2_field_completeness 校验。"""

    def test_undeclared_term_type_code(self) -> None:
        """术语使用未在 term_types 中声明的 type_code 触发 Layer 2 错误。"""
        pkg = KnowledgePackage(
            terms=(
                TermDef(
                    term_code="x",
                    term_name="X",
                    term_type_code="unknown_type",
                    library_code="L1",
                    domain_code="D1",
                ),
            ),
            relations=(
                RelationDef(
                    source_term_code="L1#unknown_type#x",
                    target_term_code="L1#unknown_type#x",
                    relation_name="x",
                    relation_category="MANY_TO_ONE",
                    cardinality="N:1",
                ),
            ),
            term_types=(TermTypeDef(type_code="object", type_name="对象", type_category=3),),
        )
        errors = validate_layer2_field_completeness(pkg)
        assert any("引用未声明的" in e for e in errors)

    def test_duplicate_type_code(self) -> None:
        """term_types 中重复 type_code 不触发 Layer 2 错误（多对象合并允许重复）。"""
        pkg = KnowledgePackage(
            terms=(
                TermDef(
                    term_code="x",
                    term_name="X",
                    term_type_code="object",
                    library_code="L1",
                    domain_code="D1",
                ),
            ),
            relations=(
                RelationDef(
                    source_term_code="L1#object#x",
                    target_term_code="L1#object#x",
                    relation_name="x",
                    relation_category="MANY_TO_ONE",
                    cardinality="N:1",
                ),
            ),
            term_types=(
                TermTypeDef(type_code="object", type_name="对象", type_category=3),
                TermTypeDef(type_code="object", type_name="对象2", type_category=3),
            ),
        )
        errors = validate_layer2_field_completeness(pkg)
        assert not any("重复" in e for e in errors)

    def test_unknown_relation_category(self) -> None:
        """非法 relation_category 触发 Layer 2 错误。"""
        pkg = KnowledgePackage(
            terms=(
                TermDef(
                    term_code="x",
                    term_name="X",
                    term_type_code="object",
                    library_code="L1",
                    domain_code="D1",
                ),
            ),
            relations=(
                RelationDef(
                    source_term_code="L1#object#x",
                    target_term_code="L1#object#x",
                    relation_name="x",
                    relation_category="BUSINESS",
                    cardinality="N:1",
                ),
            ),
            term_types=(TermTypeDef(type_code="object", type_name="对象", type_category=3),),
        )
        errors = validate_layer2_field_completeness(pkg)
        assert any("非法" in e for e in errors)

    def test_valid_package_passes(self) -> None:
        """合法字段完整包通过 Layer 2。"""
        pkg = _make_full_pkg()
        errors = validate_layer2_field_completeness(pkg)
        assert len(errors) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# validate_package 非法包聚合
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidatePackageInvalid:
    """validate_package 对非法包的聚合校验。"""

    def test_invalid_package_returns_false(self) -> None:
        """非法包返回 passed=False 并包含错误列表。"""
        pkg = KnowledgePackage(terms=(), relations=())  # 全空
        passed, errors = validate_package(pkg)
        assert passed is False
        assert len(errors) > 0

    def test_multiple_errors_aggregated(self) -> None:
        """多条违规全部收集，不短路。"""
        # 一个包同时触发 Layer 1（空 terms/relations） + SEM-001（非法 category） + SEM-007（空 cardinality）
        pkg = KnowledgePackage(
            terms=(),  # Layer 1: terms 为空
            relations=(),  # Layer 1: relations 为空
            term_types=(
                TermTypeDef(type_code="bad", type_name="非法", type_category=0),  # SEM-001
            ),
        )
        passed, errors = validate_package(pkg)
        assert passed is False
        # 至少包含 Layer 1 和 SEM-001 的错误
        has_l1 = any("Layer 1" in e for e in errors)
        has_sem001 = any("SEM-001" in e for e in errors)
        assert has_l1, f"Missing Layer 1 errors in: {errors}"
        assert has_sem001, f"Missing SEM-001 errors in: {errors}"
