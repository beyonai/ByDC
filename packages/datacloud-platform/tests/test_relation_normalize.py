"""测试 relation 归一化 + collect/submit 全链路。

只测核心逻辑，不依赖外部服务。
"""

from __future__ import annotations

import pytest

from datacloud_platform.adapters.data_adapter._base import _normalize_entity


# ── 测试 1: _normalize_entity("relation") 修正 ──────────────────────────


def test_normalize_relation_maps_relation_cardinality_to_relation_type() -> None:
    """relationCardinality → relation_type，不再输出 relation_cardinality。"""
    data = {
        "relationCode": "rel_test",
        "relationCardinality": "MANY_TO_ONE",
        "relationDesc": "测试描述",
        "sourceObjectCode": "obj_a",
        "targetObjectCode": "obj_b",
    }
    result = _normalize_entity("relation", data, for_storage=True)
    assert result["relation_type"] == "MANY_TO_ONE"
    assert "relation_cardinality" not in result  # 不再输出旧 key


def test_normalize_relation_maps_relation_desc_to_description() -> None:
    """relationDesc → description，不再输出 relation_desc。"""
    data = {
        "relationCode": "rel_test",
        "relationCardinality": "ONE_TO_MANY",
        "relationDesc": "测试描述",
        "sourceObjectCode": "obj_a",
        "targetObjectCode": "obj_b",
    }
    result = _normalize_entity("relation", data, for_storage=True)
    assert result["description"] == "测试描述"
    assert "relation_desc" not in result


def test_normalize_relation_extracts_join_keys_from_attribute() -> None:
    """从 attribute.join_keys 提取 join_keys 到顶层。"""
    data = {
        "relationCode": "rel_test",
        "relationCardinality": "MANY_TO_ONE",
        "sourceObjectCode": "obj_a",
        "targetObjectCode": "obj_b",
        "attribute": {
            "join_keys": [
                {"sourceField": "opp_id", "targetField": "id", "joinType": "LEFT"}
            ]
        },
    }
    result = _normalize_entity("relation", data, for_storage=True)
    assert result["join_keys"] == [
        {"sourceField": "opp_id", "targetField": "id", "joinType": "LEFT"}
    ]


def test_normalize_relation_extracts_cascade_delete_from_attribute() -> None:
    data = {
        "relationCode": "feature_belongs_to_product",
        "relationCardinality": "MANY_TO_ONE",
        "sourceObjectCode": "feature",
        "targetObjectCode": "product",
        "attribute": {
            "join_keys": [{"sourceField": "product_code", "targetField": "code"}],
            "cascade_delete": True,
        },
    }

    result = _normalize_entity("relation", data, for_storage=True)

    assert result["cascade_delete"] is True
    assert result["attribute"]["cascade_delete"] is True


def test_build_relation_attribute_preserves_extensions() -> None:
    from datacloud_platform.mixins.ontology_build import _build_relation_attribute

    result = _build_relation_attribute(
        {
            "attribute": {"custom": "kept"},
            "join_keys": [{"sourceField": "product_code", "targetField": "code"}],
            "cascade_delete": True,
        }
    )

    assert result == {
        "custom": "kept",
        "join_keys": [{"sourceField": "product_code", "targetField": "code"}],
        "cascade_delete": True,
    }


def test_build_relation_attribute_uses_attribute_fallbacks() -> None:
    from datacloud_platform.mixins.ontology_build import _build_relation_attribute

    result = _build_relation_attribute(
        {
            "relation_type": "MANY_TO_ONE",
            "attribute": {
                "custom": "kept",
                "join_keys": [
                    {"sourceField": "product_code", "targetField": "code"}
                ],
                "cascade_delete": True,
            },
        }
    )

    assert result["join_keys"] == [
        {"sourceField": "product_code", "targetField": "code"}
    ]
    assert result["cascade_delete"] is True
    assert result["custom"] == "kept"


def test_build_relation_attribute_rejects_ambiguous_cascade_direction() -> None:
    from datacloud_platform.mixins.ontology_build import _build_relation_attribute

    with pytest.raises(ValueError, match="MANY_TO_ONE"):
        _build_relation_attribute(
            {
                "relation_type": "ONE_TO_MANY",
                "cascade_delete": True,
            }
        )


def test_normalize_relation_no_attribute_no_join_keys() -> None:
    """没有 attribute 时不生成 join_keys。"""
    data = {
        "relationCode": "rel_test",
        "relationCardinality": "ONE_TO_ONE",
        "sourceObjectCode": "obj_a",
        "targetObjectCode": "obj_b",
    }
    result = _normalize_entity("relation", data, for_storage=True)
    assert "join_keys" not in result


def test_normalize_relation_accepts_new_field_names() -> None:
    """直接传 relation_type 和 description（OWL 格式）也能正确归一化。"""
    data = {
        "relation_code": "rel_test",
        "relation_type": "MANY_TO_MANY",
        "description": "直接描述",
        "source_class": "cls_a",
        "target_class": "cls_b",
        "join_keys": [{"sourceField": "a_id", "targetField": "b_id"}],
    }
    result = _normalize_entity("relation", data, for_storage=True)
    assert result["relation_type"] == "MANY_TO_MANY"
    assert result["description"] == "直接描述"
    assert result["source_class"] == "cls_a"
    assert result["target_class"] == "cls_b"
    assert result["join_keys"] == [{"sourceField": "a_id", "targetField": "b_id"}]


def test_normalize_relation_source_class_fallback() -> None:
    """source_class 作为 sourceObjectCode 的 fallback。"""
    data = {
        "relationCode": "rel_test",
        "relationCardinality": "MANY_TO_ONE",
        "source_class": "from_class",
        "target_class": "to_class",
    }
    result = _normalize_entity("relation", data, for_storage=True)
    assert result["source_class"] == "from_class"
    assert result["target_class"] == "to_class"


def test_normalize_relation_owner_type_and_user_code() -> None:
    """ownerType/userCode 正确映射为 owner_type/user_code。"""
    data = {
        "relationCode": "rel_test",
        "relationCardinality": "ONE_TO_ONE",
        "sourceObjectCode": "a",
        "targetObjectCode": "b",
        "ownerType": "personal",
        "userCode": "user123",
    }
    result = _normalize_entity("relation", data, for_storage=True)
    assert result["owner_type"] == "personal"
    assert result["user_code"] == "user123"


# ── 测试 2: 收集阶段 relation 归一化（mock workspace store）──────────


class _FakeStore:
    """模拟 WorkspaceStore，内存存取。"""

    def __init__(self) -> None:
        self._data: dict[str, dict] = {}

    def save(self, key: str, state: dict, ttl: int = 3600) -> None:
        self._data[key] = state

    def load(self, key: str) -> dict:
        return self._data.get(key, {}).copy()

    def delete(self, key: str) -> None:
        self._data.pop(key, None)


@pytest.fixture
def fake_workspace_store(monkeypatch: pytest.MonkeyPatch) -> _FakeStore:
    """替换 get_workspace_store 为内存假实现。"""
    store = _FakeStore()

    def _fake_get() -> _FakeStore:
        return store

    # 替换 ontology_build 模块中已导入的引用
    monkeypatch.setattr(
        "datacloud_knowledge.ingestion.ontology_build.get_workspace_store",
        _fake_get,
    )
    return store


def test_collect_object_with_relations_normalize_source_class(
    fake_workspace_store: _FakeStore,
) -> None:
    """收集对象时 object_relations 的 source_class → source_object_code 归一化。"""
    from datacloud_knowledge.ingestion.ontology_build import OntologyBuildSession

    session = OntologyBuildSession(user_code="test_user")
    result = session.collect_object_info(
        entity_code="by_project",
        entity_name="项目",
        entity_desc="项目管理",
        fields=[
            {"property_code": "id", "property_name": "ID", "data_type": "INTEGER"},
            {"property_code": "name", "property_name": "名称", "data_type": "STRING"},
        ],
        object_relations=[
            {
                "source_class": "by_project",
                "target_class": "by_opportunity",
                "relation_code": "rel_project_to_opp",
                "relation_name": "项目关联商机",
                "relation_type": "MANY_TO_ONE",
                "join_keys": [
                    {"sourceField": "opp_id", "targetField": "id", "joinType": "LEFT"}
                ],
                "description": "项目与商机的关联",
            }
        ],
    )

    rels = result["object_relations"]
    assert len(rels) == 1
    rel = rels[0]
    assert rel["source_object_code"] == "by_project"
    assert rel["target_object_code"] == "by_opportunity"
    assert rel["relation_code"] == "rel_project_to_opp"
    assert rel["relation_name"] == "项目关联商机"
    assert rel["relation_type"] == "MANY_TO_ONE"
    assert rel["description"] == "项目与商机的关联"
    assert rel["join_keys"] == [
        {"sourceField": "opp_id", "targetField": "id", "joinType": "LEFT"}
    ]


def test_collect_object_rejects_non_boolean_cascade_delete(
    fake_workspace_store: _FakeStore,
) -> None:
    from datacloud_knowledge.ingestion.ontology_build import OntologyBuildSession

    session = OntologyBuildSession(user_code="test_user")
    with pytest.raises(ValueError, match="cascade_delete"):
        session.collect_object_info(
            entity_code="by_feature",
            entity_name="特性",
            fields=[
                {
                    "property_code": "product_code",
                    "property_name": "产品编码",
                    "data_type": "STRING",
                }
            ],
            object_relations=[
                {
                    "target_object_code": "by_product",
                    "relation_type": "MANY_TO_ONE",
                    "join_keys": [
                        {"sourceField": "product_code", "targetField": "code"}
                    ],
                    "cascade_delete": "true",
                }
            ],
        )


def test_collect_object_rejects_required_cascade_join_key(
    fake_workspace_store: _FakeStore,
) -> None:
    from datacloud_knowledge.ingestion.ontology_build import OntologyBuildSession

    session = OntologyBuildSession(user_code="test_user")
    with pytest.raises(ValueError, match="必须允许清空"):
        session.collect_object_info(
            entity_code="by_feature",
            entity_name="特性",
            fields=[
                {
                    "property_code": "product_code",
                    "property_name": "产品编码",
                    "data_type": "STRING",
                    "is_required": True,
                }
            ],
            object_relations=[
                {
                    "relation_code": "feature_belongs_to_product",
                    "target_object_code": "by_product",
                    "relation_type": "MANY_TO_ONE",
                    "join_keys": [
                        {"sourceField": "product_code", "targetField": "code"}
                    ],
                    "cascade_delete": True,
                }
            ],
        )


def test_collect_object_accepts_nullable_cascade_join_key(
    fake_workspace_store: _FakeStore,
) -> None:
    from datacloud_knowledge.ingestion.ontology_build import OntologyBuildSession

    session = OntologyBuildSession(user_code="test_user")
    result = session.collect_object_info(
        entity_code="by_feature",
        entity_name="特性",
        fields=[
            {
                "property_code": "product_code",
                "property_name": "产品编码",
                "data_type": "STRING",
                "is_required": False,
            }
        ],
        object_relations=[
            {
                "relation_code": "feature_belongs_to_product",
                "target_object_code": "by_product",
                "relation_type": "MANY_TO_ONE",
                "join_keys": [
                    {"sourceField": "product_code", "targetField": "code"}
                ],
                "cascade_delete": True,
            }
        ],
    )

    assert result["object_relations"][0]["cascade_delete"] is True


def test_collect_view_with_relations_normalize_source_class(
    fake_workspace_store: _FakeStore,
) -> None:
    """收集视图时 object_relations 的 source_class → source_object_code 归一化。"""
    from datacloud_knowledge.ingestion.ontology_build import OntologyBuildSession

    session = OntologyBuildSession(user_code="test_user")
    result = session.collect_view_info(
        view_code="my_view",
        view_name="我的视图",
        object_codes=["by_project", "by_opportunity"],
        object_relations=[
            {
                "source_class": "by_project",
                "target_class": "by_opportunity",
                "relation_code": "rel_project_to_opp",
                "relation_name": "项目关联商机",
                "relation_type": "MANY_TO_ONE",
                "join_keys": [{"sourceField": "opp_id", "targetField": "id"}],
            }
        ],
    )

    rels = result["object_relations"]
    assert len(rels) == 1
    rel = rels[0]
    assert rel["source_object_code"] == "by_project"
    assert rel["target_object_code"] == "by_opportunity"
    assert rel["join_keys"] == [{"sourceField": "opp_id", "targetField": "id"}]


def test_collect_view_relations_dedup_by_source_target(
    fake_workspace_store: _FakeStore,
) -> None:
    """dedup key 只用 source/target，不因缺少 field_code 导致碰撞。"""
    from datacloud_knowledge.ingestion.ontology_build import OntologyBuildSession

    session = OntologyBuildSession(user_code="test_user")
    # 第一次收集
    session.collect_view_info(
        view_code="my_view",
        object_relations=[
            {
                "source_class": "by_project",
                "target_class": "by_opportunity",
                "relation_name": "v1",
            }
        ],
    )
    # 第二次收集，同一 source/target 应该覆盖，不同 source/target 应该追加
    result = session.collect_view_info(
        view_code="my_view",
        object_relations=[
            {
                "source_class": "by_project",
                "target_class": "by_opportunity",
                "relation_name": "v2",  # 覆盖
            },
            {
                "source_class": "by_opportunity",
                "target_class": "by_project",
                "relation_name": "反向关系",  # 新增
            },
        ],
    )

    rels = result["object_relations"]
    assert len(rels) == 2
    names = {r["relation_name"] for r in rels}
    assert names == {"v2", "反向关系"}


# ── 测试 3: load_from_content 能正确读取修正后的 key ────────────────────


def test_ontology_loader_reads_relation_type_and_join_keys() -> None:
    """OntologyLoader.load_from_content 从修正后的 key 正确读取。"""
    from datacloud_data_sdk.ontology.loader import OntologyLoader

    content = {
        "objects": [
            {
                "object_code": "by_project",
                "object_name": "项目",
                "source_type": "DB",
                "fields": [],
                "actions": [],
            },
            {
                "object_code": "by_opportunity",
                "object_name": "商机",
                "source_type": "DB",
                "fields": [],
                "actions": [],
            },
        ],
        "relations": [
            {
                "relation_code": "rel_project_to_opp",
                "relation_name": "项目关联商机",
                "source_class": "by_project",
                "target_class": "by_opportunity",
                "relation_type": "MANY_TO_ONE",
                "join_keys": [{"sourceField": "opp_id", "targetField": "id"}],
                "description": "项目与商机关联",
            }
        ],
    }
    loader = OntologyLoader()
    loader.load_from_content(content)
    rels = loader.get_ontology_relations()
    assert len(rels) == 1
    rel = rels[0]
    assert rel.relation_code == "rel_project_to_opp"
    assert rel.relation_type == "MANY_TO_ONE"
    assert rel.source_class == "by_project"
    assert rel.target_class == "by_opportunity"
    assert rel.join_keys == [{"sourceField": "opp_id", "targetField": "id"}]
    assert rel.description == "项目与商机关联"
