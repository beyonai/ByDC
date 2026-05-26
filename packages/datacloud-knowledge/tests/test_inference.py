"""推断层单元测试 — normalize_source_type / normalize_joinkeys / infer_relations 等。

测试 OWL 导入器推断层的格式归一化、关系推断和 Action 引用完整性校验。
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from datacloud_knowledge.ingestion.owl_import.importer.inference import (
    apply_inference,
    infer_relations_from_definitions,
    normalize_entities,
    normalize_entity,
    normalize_joinkeys,
    normalize_source_type,
    normalize_term_code_path,
    validate_action_refs,
)

# ═══════════════════════════════════════════════════════════════════════════════
# normalize_source_type 测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestNormalizeSourceType:
    """normalize_source_type — 中文类型→英文标识。"""

    def test_object_mapping(self) -> None:
        """中文"对象"→"object"。"""
        assert normalize_source_type("对象") == "object"

    def test_view_mapping(self) -> None:
        """中文"视图"→"view"。"""
        assert normalize_source_type("视图") == "view"

    def test_scene_to_view_mapping(self) -> None:
        """中文"场景"→"view"（历史别名）。"""
        assert normalize_source_type("场景") == "view"

    def test_action_mapping(self) -> None:
        """中文"动作"→"action"。"""
        assert normalize_source_type("动作") == "action"

    def test_prop_mapping(self) -> None:
        """中文"属性"→"prop"。"""
        assert normalize_source_type("属性") == "prop"

    def test_english_passthrough(self) -> None:
        """英文值直接透传。"""
        assert normalize_source_type("object") == "object"
        assert normalize_source_type("view") == "view"
        assert normalize_source_type("prop") == "prop"
        assert normalize_source_type("action") == "action"

    def test_none_returns_empty(self) -> None:
        """None 输入返回空字符串。"""
        assert normalize_source_type(None) == ""

    def test_empty_string_returns_empty(self) -> None:
        """空字符串返回空字符串。"""
        assert normalize_source_type("") == ""

    def test_whitespace_stripped(self) -> None:
        """前后空格被去除后映射。"""
        assert normalize_source_type(" 对象 ") == "object"

    def test_term_type_mapping(self) -> None:
        """中文"术语类型"/"术语"→"term_type"。"""
        assert normalize_source_type("术语类型") == "term_type"
        assert normalize_source_type("术语") == "term_type"


# ═══════════════════════════════════════════════════════════════════════════════
# normalize_term_code_path 测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestNormalizeTermCodePath:
    """normalize_term_code_path — path 小写化。"""

    def test_single_level_lowercase(self) -> None:
        """单级路径：OBJECT#by_customer → object#by_customer。"""
        assert normalize_term_code_path("OBJECT#by_customer") == "object#by_customer"

    def test_multi_level_lowercase(self) -> None:
        """多级路径全部小写化。"""
        result = normalize_term_code_path("VIEW#SCENE_SALES#FIELD#opp_name")
        assert result == "view#scene_sales#field#opp_name"

    def test_strip_and_lower(self) -> None:
        """去除空格并小写化。"""
        assert normalize_term_code_path("  L1#OBJECT#Code  ") == "l1#object#code"

    def test_none_returns_empty(self) -> None:
        """None 返回空字符串。"""
        assert normalize_term_code_path(None) == ""

    def test_empty_returns_empty(self) -> None:
        """空字符串返回空字符串。"""
        assert normalize_term_code_path("") == ""

    def test_already_lowercase_passthrough(self) -> None:
        """已小写路径直接返回（小写化）。"""
        assert normalize_term_code_path("l1#object#code") == "l1#object#code"


# ═══════════════════════════════════════════════════════════════════════════════
# normalize_joinkeys 测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestNormalizeJoinkeys:
    """normalize_joinkeys — from_field→sourceField, to_field→targetField。"""

    def test_field_mapping(self) -> None:
        """from_field → sourceField, to_field → targetField。"""
        result = normalize_joinkeys(
            [
                {"from_field": "b_id", "to_field": "id"},
            ]
        )
        assert result == [{"sourceField": "b_id", "targetField": "id"}]

    def test_partial_mapping(self) -> None:
        """混合字段：只映射已知的，其余通过。"""
        result = normalize_joinkeys(
            [
                {"from_field": "a", "other_key": "v", "to_field": "b"},
            ]
        )
        assert result == [{"sourceField": "a", "other_key": "v", "targetField": "b"}]

    def test_multiple_items(self) -> None:
        """多条 joinkeys 均正确映射。"""
        result = normalize_joinkeys(
            [
                {"from_field": "a1", "to_field": "b1"},
                {"from_field": "a2", "to_field": "b2"},
            ]
        )
        assert len(result) == 2
        assert result[0] == {"sourceField": "a1", "targetField": "b1"}
        assert result[1] == {"sourceField": "a2", "targetField": "b2"}

    def test_empty_list(self) -> None:
        """空列表返回空列表。"""
        assert normalize_joinkeys([]) == []

    def test_none_returns_empty(self) -> None:
        """None 返回空列表。"""
        assert normalize_joinkeys(None) == []

    def test_non_dict_skipped(self) -> None:
        """非 dict 项被跳过。"""
        result = normalize_joinkeys(["not_a_dict", {"from_field": "x", "to_field": "y"}])
        assert result == [{"sourceField": "x", "targetField": "y"}]

    def test_no_known_fields_passthrough(self) -> None:
        """无已知字段的 dict 原样保留。"""
        result = normalize_joinkeys([{"unknown": "val"}])
        assert result == [{"unknown": "val"}]


# ═══════════════════════════════════════════════════════════════════════════════
# normalize_entity 测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestNormalizeEntity:
    """normalize_entity — 单 entity 全字段归一化。"""

    def test_returns_new_dict(self) -> None:
        """不修改输入 dict。"""
        original = {"source_type": "对象", "key": "val"}
        result = normalize_entity(original)
        assert original["source_type"] == "对象"
        assert result["source_type"] == "object"

    def test_source_type_normalized(self) -> None:
        """source_type 中文→英文。"""
        result = normalize_entity({"entity_type": "object", "source_type": "对象"})
        assert result["source_type"] == "object"

    def test_target_type_normalized(self) -> None:
        """target_type 中文→英文。"""
        result = normalize_entity({"entity_type": "relation", "target_type": "属性"})
        assert result["target_type"] == "prop"

    def test_term_code_path_lowercased(self) -> None:
        """term_code_path 小写化。"""
        result = normalize_entity({"entity_type": "term", "term_code_path": "OBJECT#by_customer"})
        assert result["term_code_path"] == "object#by_customer"

    def test_term_type_code_path_lowercased(self) -> None:
        """term_type_code_path 小写化。"""
        result = normalize_entity(
            {"entity_type": "term_type", "term_type_code_path": "TYPE#OBJECT"}
        )
        assert result["term_type_code_path"] == "type#object"

    def test_joinkeys_normalized(self) -> None:
        """joinkeys 字段名标准化。"""
        result = normalize_entity(
            {
                "entity_type": "relation",
                "joinkeys": [{"from_field": "a", "to_field": "b"}],
            }
        )
        assert result["joinkeys"] == [{"sourceField": "a", "targetField": "b"}]

    def test_joinkeys_json_string_parsed(self) -> None:
        """joinkeys 为 JSON 字符串时自动解析。"""
        result = normalize_entity(
            {
                "entity_type": "relation",
                "joinkeys": '[{"from_field":"a","to_field":"b"}]',
            }
        )
        assert result["joinkeys"] == [{"sourceField": "a", "targetField": "b"}]

    def test_invalid_joinkeys_json_fallback(self) -> None:
        """非法 JSON 的 joinkeys 回退为空列表。"""
        result = normalize_entity(
            {
                "entity_type": "relation",
                "joinkeys": "not-valid-json",
            }
        )
        assert result["joinkeys"] == []

    def test_other_fields_passthrough(self) -> None:
        """非归一化字段原样透传。"""
        result = normalize_entity({"entity_type": "view", "view_code": "scene_sales"})
        assert result["view_code"] == "scene_sales"

    def test_all_normalizations_together(self) -> None:
        """所有归一化同时生效。"""
        entity: dict[str, Any] = {
            "entity_type": "object",
            "source_type": "对象",
            "term_code_path": "OBJECT#by_customer",
            "joinkeys": [{"from_field": "id"}],
            "object_code": "by_customer",
        }
        result = normalize_entity(entity)
        assert result["source_type"] == "object"
        assert result["term_code_path"] == "object#by_customer"
        assert result["joinkeys"] == [{"sourceField": "id"}]
        assert result["object_code"] == "by_customer"


# ═══════════════════════════════════════════════════════════════════════════════
# normalize_entities 测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestNormalizeEntities:
    """normalize_entities — 批量归一化。"""

    def test_batch_normalization(self) -> None:
        """多个 entity 各自独立归一化。"""
        entities: list[dict[str, Any]] = [
            {"entity_type": "object", "source_type": "对象"},
            {"entity_type": "view", "source_type": "视图"},
            {"entity_type": "prop", "source_type": "属性"},
        ]
        result = normalize_entities(entities)
        assert result[0]["source_type"] == "object"
        assert result[1]["source_type"] == "view"
        assert result[2]["source_type"] == "prop"
        # 原始输入不被修改
        assert entities[0]["source_type"] == "对象"

    def test_empty_list(self) -> None:
        """空列表返回空列表。"""
        assert normalize_entities([]) == []

    def test_original_unmodified(self) -> None:
        """原始列表不被修改。"""
        entities: list[dict[str, Any]] = [{"source_type": "对象"}]
        normalize_entities(entities)
        assert entities[0]["source_type"] == "对象"


# ═══════════════════════════════════════════════════════════════════════════════
# validate_action_refs 测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidateActionRefs:
    """validate_action_refs — action_refs 引用完整性校验。"""

    @staticmethod
    def _make_entity(
        entity_type: str,
        term_code: str,
        action_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        """构造测试用 entity dict。"""
        entity: dict[str, Any] = {
            "entity_type": entity_type,
            "term_code": term_code,
        }
        if action_refs is not None:
            entity["action_refs"] = action_refs
        return entity

    def test_actions_dir_missing(self) -> None:
        """actions 目录不存在时返回空错误（不校验）。"""
        with tempfile.TemporaryDirectory() as tmp:
            errors = validate_action_refs(
                entities=[],
                actions_dir=Path(tmp) / "nonexistent",
            )
            assert errors == []

    def test_no_action_refs_passes(self) -> None:
        """实体无 action_refs 时通过。"""
        with tempfile.TemporaryDirectory() as tmp:
            actions_dir = Path(tmp) / "actions"
            errors = validate_action_refs(
                entities=[self._make_entity("object", "obj_a")],
                actions_dir=actions_dir,
            )
            assert errors == []

    def test_valid_refs_passes(self) -> None:
        """action_refs 对应的文件存在时通过。"""
        with tempfile.TemporaryDirectory() as tmp:
            actions_dir = Path(tmp) / "actions"
            actions_dir.mkdir()
            (actions_dir / "get_customer.owl").write_text("<xml/>")
            (actions_dir / "update_customer.owl").write_text("<xml/>")

            errors = validate_action_refs(
                entities=[self._make_entity("object", "by_customer", ["get_customer"])],
                actions_dir=actions_dir,
            )
            assert errors == []

    def test_missing_ref_triggers_error(self) -> None:
        """引用不存在的 action 文件触发错误。"""
        with tempfile.TemporaryDirectory() as tmp:
            actions_dir = Path(tmp) / "actions"
            actions_dir.mkdir()
            (actions_dir / "get_customer.owl").write_text("<xml/>")

            errors = validate_action_refs(
                entities=[self._make_entity("object", "by_customer", ["missing_action"])],
                actions_dir=actions_dir,
            )
            assert len(errors) >= 1
            assert "missing_action" in errors[0]

    def test_multiple_missing_refs(self) -> None:
        """多个缺失引用全部收集。"""
        with tempfile.TemporaryDirectory() as tmp:
            actions_dir = Path(tmp) / "actions"
            actions_dir.mkdir()
            # 创建至少一个 action 文件以启用校验循环
            (actions_dir / "existing.owl").write_text("<xml/>")

            errors = validate_action_refs(
                entities=[self._make_entity("object", "obj", ["a1", "a2", "a3"])],
                actions_dir=actions_dir,
            )
            assert len(errors) == 3

    def test_view_entity_also_checked(self) -> None:
        """view 类型实体的 action_refs 同样校验。"""
        with tempfile.TemporaryDirectory() as tmp:
            actions_dir = Path(tmp) / "actions"
            actions_dir.mkdir()
            # 创建至少一个 action 文件以启用校验循环
            (actions_dir / "existing.owl").write_text("<xml/>")

            errors = validate_action_refs(
                entities=[self._make_entity("view", "scene_x", ["missing"])],
                actions_dir=actions_dir,
            )
            assert len(errors) >= 1

    def test_non_object_view_ignored(self) -> None:
        """prop/relation 等非 object/view 类型跳过。"""
        with tempfile.TemporaryDirectory() as tmp:
            actions_dir = Path(tmp) / "actions"

            errors = validate_action_refs(
                entities=[self._make_entity("prop", "prop_x", ["missing"])],
                actions_dir=actions_dir,
            )
            assert errors == []

    def test_action_refs_json_string(self) -> None:
        """action_refs 为 JSON 字符串时正确解析。"""
        import json

        with tempfile.TemporaryDirectory() as tmp:
            actions_dir = Path(tmp) / "actions"
            actions_dir.mkdir()
            (actions_dir / "act1.owl").write_text("<xml/>")

            entity = self._make_entity("object", "obj")
            entity["action_refs"] = json.dumps(["act1"])
            errors = validate_action_refs(
                entities=[entity],
                actions_dir=actions_dir,
            )
            assert errors == []

    def test_owl_suffix_stripped(self) -> None:
        """action_ref 中 .owl 后缀自动去除。"""
        with tempfile.TemporaryDirectory() as tmp:
            actions_dir = Path(tmp) / "actions"
            actions_dir.mkdir()
            (actions_dir / "my_action.owl").write_text("<xml/>")

            errors = validate_action_refs(
                entities=[self._make_entity("object", "obj", ["my_action.owl"])],
                actions_dir=actions_dir,
            )
            assert errors == []

    def test_empty_action_refs_list_passes(self) -> None:
        """空 action_refs 列表通过。"""
        with tempfile.TemporaryDirectory() as tmp:
            actions_dir = Path(tmp) / "actions"
            actions_dir.mkdir()

            errors = validate_action_refs(
                entities=[self._make_entity("object", "obj", [])],
                actions_dir=actions_dir,
            )
            assert errors == []


# ═══════════════════════════════════════════════════════════════════════════════
# infer_relations_from_definitions 测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestInferRelationsFromDefinitions:
    """infer_relations_from_definitions — 从定义文件推断关系。"""

    def test_object_with_fields_produces_has_field(self) -> None:
        """object 的 fields 数组产生 HAS_FIELD 关系。"""
        entities: list[dict[str, Any]] = [
            {
                "entity_type": "object",
                "object_code": "by_customer",
                "fields": [
                    {"fieldCode": "customer_name", "property_code": ""},
                    {"fieldCode": "customer_code", "property_code": ""},
                ],
            },
        ]
        result = infer_relations_from_definitions(entities)
        assert len(result) == 2
        for rel in result:
            assert rel["entity_type"] == "relation"
            assert rel["relation_category"] == "HAS_FIELD"
            assert rel["source_type"] == "object"
            assert rel["source_code"] == "by_customer"
            assert rel["target_type"] == "prop"
            assert rel["_inferred"] is True

    def test_view_with_object_codes_produces_has_object(self) -> None:
        """view 的 object_codes 产生 HAS_OBJECT 关系。"""
        entities: list[dict[str, Any]] = [
            {
                "entity_type": "view",
                "view_code": "scene_sales",
                "object_codes": ["by_customer", "by_project"],
            },
        ]
        result = infer_relations_from_definitions(entities)
        assert len(result) == 2
        for rel in result:
            assert rel["relation_category"] == "HAS_OBJECT"
            assert rel["source_type"] == "view"
            assert rel["source_code"] == "scene_sales"
            assert rel["target_type"] == "object"
            assert rel["_inferred"] is True

    def test_view_with_scene_field_produces_has_field(self) -> None:
        """view 的 fields (SceneField) 产生 HAS_FIELD 关系。"""
        entities: list[dict[str, Any]] = [
            {
                "entity_type": "view",
                "view_code": "scene_sales",
                "fields": [
                    {"fieldCode": "opp_name"},
                    {"fieldCode": "customer_name"},
                ],
            },
        ]
        result = infer_relations_from_definitions(entities)
        assert len(result) == 2
        for rel in result:
            assert rel["relation_category"] == "HAS_FIELD"
            assert rel["source_type"] == "view"
            assert rel["_inferred"] is True

    def test_view_with_both_object_codes_and_fields(self) -> None:
        """view 同时有 object_codes 和 fields：两者都产生关系。"""
        entities: list[dict[str, Any]] = [
            {
                "entity_type": "view",
                "view_code": "scene_sales",
                "object_codes": ["by_customer"],
                "fields": [{"fieldCode": "opp_name"}],
            },
        ]
        result = infer_relations_from_definitions(entities)
        categories = {r["relation_category"] for r in result}
        assert "HAS_OBJECT" in categories
        assert "HAS_FIELD" in categories
        assert len(result) == 2

    def test_scene_entity_type_also_handled(self) -> None:
        """entity_type="scene" 也按 view 处理（兼容性）。"""
        entities: list[dict[str, Any]] = [
            {
                "entity_type": "scene",
                "object_code": "scene_x",
                "object_codes": ["by_customer"],
            },
        ]
        result = infer_relations_from_definitions(entities)
        assert len(result) == 1
        assert result[0]["relation_category"] == "HAS_OBJECT"

    def test_empty_entities(self) -> None:
        """空实体列表返回空关系。"""
        assert infer_relations_from_definitions([]) == []

    def test_no_relevant_entities(self) -> None:
        """无 object/view 实体的列表不产生关系。"""
        entities: list[dict[str, Any]] = [
            {"entity_type": "prop", "term_code": "x"},
            {"entity_type": "relation", "source_code": "a"},
        ]
        assert infer_relations_from_definitions(entities) == []

    def test_field_without_code_skipped(self) -> None:
        """无 fieldCode 的 field 被跳过。"""
        entities: list[dict[str, Any]] = [
            {
                "entity_type": "object",
                "object_code": "obj",
                "fields": [
                    {"fieldCode": "", "property_code": ""},
                    {"fieldCode": "valid_field"},
                ],
            },
        ]
        result = infer_relations_from_definitions(entities)
        assert len(result) == 1
        assert result[0]["target_code"] == "valid_field"

    def test_object_codes_json_string(self) -> None:
        """object_codes 为 JSON 字符串时正确解析。"""
        import json

        entities: list[dict[str, Any]] = [
            {
                "entity_type": "view",
                "view_code": "scene_x",
                "object_codes": json.dumps(["by_customer", "by_project"]),
            },
        ]
        result = infer_relations_from_definitions(entities)
        assert len(result) == 2

    def test_object_codes_comma_separated(self) -> None:
        """object_codes 逗号分隔字符串格式。"""
        entities: list[dict[str, Any]] = [
            {
                "entity_type": "view",
                "view_code": "scene_x",
                "object_codes": "by_customer,by_project,by_task",
            },
        ]
        result = infer_relations_from_definitions(entities)
        assert len(result) == 3

    def test_cardinality_default(self) -> None:
        """推断的关系默认 cardinality 为 1:N。"""
        entities: list[dict[str, Any]] = [
            {
                "entity_type": "object",
                "object_code": "obj",
                "fields": [{"fieldCode": "f1"}],
            },
        ]
        result = infer_relations_from_definitions(entities)
        assert result[0]["cardinality"] == "1:N"

    def test_relation_type_field(self) -> None:
        """推断的关系包含 relation_type 字段匹配 relation_category。"""
        entities: list[dict[str, Any]] = [
            {
                "entity_type": "object",
                "object_code": "obj",
                "fields": [{"fieldCode": "f1"}],
            },
        ]
        result = infer_relations_from_definitions(entities)
        assert result[0]["relation_type"] == result[0]["relation_category"]


# ═══════════════════════════════════════════════════════════════════════════════
# apply_inference 测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestApplyInference:
    """apply_inference — 全流程推断（归一化 + 关系推断 + action 校验）。"""

    def test_full_pipeline(self) -> None:
        """全流程：归一化 → 推断关系 → action 校验。"""
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = Path(tmp)
            actions_dir = package_dir / "actions"
            actions_dir.mkdir()
            (actions_dir / "get_customer.owl").write_text("<xml/>")

            entities: list[dict[str, Any]] = [
                {
                    "entity_type": "object",
                    "source_type": "对象",
                    "term_code_path": "OBJECT#by_customer",
                    "object_code": "by_customer",
                    "fields": [
                        {"fieldCode": "customer_name"},
                    ],
                    "action_refs": ["get_customer"],
                },
            ]

            normalized, errors = apply_inference(package_dir, entities)
            # errors 为空
            assert errors == []
            # 包含原始 entity（归一化后）+ 推断的关系
            assert len(normalized) >= 2
            # 归一化生效
            obj_entities = [e for e in normalized if e["entity_type"] == "object"]
            assert any(e["source_type"] == "object" for e in obj_entities)
            assert any(e["term_code_path"] == "object#by_customer" for e in obj_entities)
            # 推断的关系存在
            rel_entities = [e for e in normalized if e["entity_type"] == "relation"]
            assert len(rel_entities) >= 1

    def test_step2_no_inference_when_no_relevant_entities(self) -> None:
        """无 object/view 实体时不推断关系。"""
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = Path(tmp)
            entities: list[dict[str, Any]] = [
                {"entity_type": "prop", "source_type": "属性", "term_code": "x"},
            ]
            normalized, errors = apply_inference(package_dir, entities)
            assert len(normalized) == 1
            assert errors == []

    def test_step3_action_errors_collected(self) -> None:
        """action 校验错误被收集但不断路。"""
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = Path(tmp)
            actions_dir = package_dir / "actions"
            actions_dir.mkdir()
            # 创建至少一个 action 文件以启用校验循环
            (actions_dir / "known.owl").write_text("<xml/>")

            entities: list[dict[str, Any]] = [
                {
                    "entity_type": "object",
                    "object_code": "obj",
                    "action_refs": ["missing_action"],
                },
            ]

            normalized, errors = apply_inference(package_dir, entities)
            # 归一化依然完成
            assert len(normalized) >= 1
            # action 校验错误已收集
            assert len(errors) >= 1

    def test_original_list_unmodified(self) -> None:
        """原始 entities 列表不被修改。"""
        with tempfile.TemporaryDirectory() as tmp:
            package_dir = Path(tmp)
            entities: list[dict[str, Any]] = [
                {"entity_type": "object", "source_type": "对象"},
            ]
            original_first = entities[0]
            apply_inference(package_dir, entities)
            assert entities[0]["source_type"] == "对象"
            assert entities[0] is original_first
