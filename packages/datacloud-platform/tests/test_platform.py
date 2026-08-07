"""Tests for DatacloudPlatform convenience methods — multi-base API."""

from __future__ import annotations

from datacloud_platform import DatacloudPlatform
from datacloud_platform.adapters.json_entity_store import JsonEntityStore
from datacloud_platform.backends.registry import (
    register_backend_type,
    register_implementation,
)
from datacloud_platform.models.shared import (
    MatchCandidate,
    MatchResult,
    ObjectSummary,
)
from fakes import (
    FakeExecutionBackend,
    FakeOntologyBackend,
    FakeStorageBackend,
    FakeTermBackend,
)


LOCAL = "local-base"


def test_load_ontology(platform: DatacloudPlatform) -> None:
    """load_ontology + get_objects round-trip through FakeOntologyBackend."""
    onto_local, *_ = platform._fakes  # type: ignore[attr-defined]
    onto_local._objects["test_obj"] = ObjectSummary(  # type: ignore[index]
        object_code="test_obj", object_name="测试对象"
    )
    loader = platform.load_ontology(LOCAL, "/fake/path")
    assert loader is not None
    objs = onto_local.get_objects(loader, LOCAL)
    assert len(objs) == 1
    assert objs[0].object_code == "test_obj"
    assert objs[0].object_name == "测试对象"


def test_query_objects_by_knowledge_delegates_to_backend(
    platform: DatacloudPlatform,
) -> None:
    onto_local, *_ = platform._fakes  # type: ignore[attr-defined]
    onto_local._knowledge_objects = (
        [  # type: ignore[attr-defined]
            {
                "objectCode": "customer",
                "objectName": "客户",
                "baseId": LOCAL,
                "kbResourceId": "kb-1",
                "kbDirectory": "/a",
            }
        ],
        1,
    )

    items, total = platform.query_objects_by_knowledge(
        LOCAL,
        kb_resource_id="kb-1",
        kb_directories=["/a"],
        object_name="客户",
        page_index=1,
        page_size=20,
    )

    assert total == 1
    assert items[0]["baseId"] == LOCAL
    assert "properties" not in items[0]
    assert "actions" not in items[0]
    assert onto_local._knowledge_query == {  # type: ignore[attr-defined]
        "base_id": LOCAL,
        "kb_resource_id": "kb-1",
        "kb_directories": ["/a"],
        "object_name": "客户",
        "page_index": 1,
        "page_size": 20,
    }


def test_search(platform: DatacloudPlatform) -> None:
    """search() delegates to search_candidates + disambiguate on FakeTermBackend."""
    _, _, know, *_ = platform._fakes  # type: ignore[attr-defined]

    candidate = MatchCandidate(
        term_id="t1",
        term_name="销售额",
        term_type_code="metric",
        match_type="semantic",
        confidence=0.95,
        score=0.95,
    )
    know.candidates = [candidate]

    result = MatchResult(
        exact={"销售额": (candidate,)},
        fuzzy={},
    )
    know._disambiguated = [result]

    results = platform.search(LOCAL, "销售额")
    assert len(results) == 1
    assert results[0] == result


def test_store_and_retrieve(platform: DatacloudPlatform) -> None:
    """store_result + get_result round-trip through FakeStorageBackend."""
    fid = platform.store_result(LOCAL, "report", b"hello world")
    assert isinstance(fid, str)
    assert len(fid) > 0
    assert platform.get_result(LOCAL, fid) == b"hello world"


def test_backend_switching(entity_store: JsonEntityStore) -> None:
    """Registering alternate backend names and constructing a new multi-base platform works."""
    onto = FakeOntologyBackend()
    know = FakeTermBackend()
    exec_ = FakeExecutionBackend()
    stor = FakeStorageBackend()

    register_backend_type("ontology", "alt-data")
    register_backend_type("term", "alt-knowledge")
    register_backend_type("execution", "alt-exec")
    register_backend_type("storage", "alt-storage")

    register_implementation("ontology", "alt-data", lambda: onto)
    register_implementation("term", "alt-knowledge", lambda: know)
    register_implementation("execution", "alt-exec", lambda: exec_)
    register_implementation("storage", "alt-storage", lambda: stor)
    register_implementation("execution", "none", lambda: None)  # type: ignore[arg-type,return-value]
    register_implementation("storage", "none", lambda: None)  # type: ignore[arg-type,return-value]

    from datacloud_platform import OntologyBaseEntry, OntologyBaseRegistry
    from datacloud_platform.backends.presets import register_preset

    register_preset("LOCAL", {})
    registry = OntologyBaseRegistry(entity_store)
    registry.register(
        OntologyBaseEntry(
            base_id="alt-base",
            display_name="Alt Base",
            source_type="LOCAL",
            manual_backends={
                "ontology": "alt-data",
                "term": "alt-knowledge",
                "execution": "alt-exec",
                "storage": "alt-storage",
            },
        )
    )

    p = DatacloudPlatform(_base_registry=registry)
    loader = p.load_ontology("alt-base", "/path")
    assert loader is not None
