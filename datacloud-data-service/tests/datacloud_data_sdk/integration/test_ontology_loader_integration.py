"""集成测试: OntologyLoader 加载迁移后的 CRM 对象注册文件。"""

from __future__ import annotations

import pytest
from pathlib import Path

from datacloud_data_sdk.ontology.loader import OntologyLoader

REGISTRY_PATH = Path(__file__).parents[3] / "resources/ontology/crm_demo/objects_registry.json"
SCENE_PATH = Path(__file__).parents[3] / "resources/ontology/crm_demo/scene_01_data_analysis.json"

_skip_no_registry = pytest.mark.skipif(
    not REGISTRY_PATH.exists(), reason="CRM registry not found"
)


@_skip_no_registry
def test_load_crm_registry_has_objects() -> None:
    loader = OntologyLoader()
    loader.load_from_path(REGISTRY_PATH)
    classes = loader.get_ontology_classes()
    assert len(classes) >= 3


@_skip_no_registry
def test_crm_objects_have_fields() -> None:
    loader = OntologyLoader()
    loader.load_from_path(REGISTRY_PATH)
    for cls in loader.get_ontology_classes():
        assert len(cls.fields) > 0, f"{cls.object_code} has no fields"


@_skip_no_registry
def test_crm_has_relations() -> None:
    loader = OntologyLoader()
    loader.load_from_path(REGISTRY_PATH)
    rels = loader.get_ontology_relations()
    assert len(rels) >= 1


@_skip_no_registry
def test_crm_objects_source_types() -> None:
    loader = OntologyLoader()
    loader.load_from_path(REGISTRY_PATH)
    source_types = {cls.source_type for cls in loader.get_ontology_classes()}
    assert "API" in source_types
    assert "DB" in source_types


@_skip_no_registry
def test_crm_db_objects_have_table_name() -> None:
    loader = OntologyLoader()
    loader.load_from_path(REGISTRY_PATH)
    for cls in loader.get_ontology_classes():
        if cls.source_type == "DB":
            assert cls.table_name is not None, f"DB object {cls.object_code} missing table_name"
            assert cls.datasource_alias is not None, f"DB object {cls.object_code} missing datasource_alias"


@_skip_no_registry
def test_crm_actions_have_function_refs() -> None:
    loader = OntologyLoader()
    loader.load_from_path(REGISTRY_PATH)
    action_count = 0
    for cls in loader.get_ontology_classes():
        for act in cls.actions:
            action_count += 1
            assert len(act.function_refs) > 0, f"Action {act.action_code} has no function_refs"
    assert action_count > 0


@_skip_no_registry
def test_crm_relations_have_join_keys() -> None:
    loader = OntologyLoader()
    loader.load_from_path(REGISTRY_PATH)
    for rel in loader.get_ontology_relations():
        assert len(rel.join_keys) > 0, f"Relation {rel.relation_code} has no join_keys"


@_skip_no_registry
@pytest.mark.skipif(not SCENE_PATH.exists(), reason="CRM scene not found")
def test_load_scene_and_get_view() -> None:
    loader = OntologyLoader()
    loader.load_from_path(REGISTRY_PATH)
    loader.load_scene_from_path(SCENE_PATH)
    view = loader.get_view("scene_01_data_analysis")
    assert view.view_id == "scene_01_data_analysis"
    assert len(view.objects) >= 3
