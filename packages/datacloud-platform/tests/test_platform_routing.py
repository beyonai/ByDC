"""Tests for multi-base routing in DatacloudPlatform (§6.3 of architecture doc).

Verifies the 3-layer resolution per base_id: defaults → preset → manual_backends.
"""

from __future__ import annotations

import pytest

from datacloud_platform import DatacloudPlatform
from datacloud_platform.backends.presets import register_preset
from datacloud_platform.models import (
    MatchCandidate,
    MatchResult,
)

LOCAL = "local-base"
REMOTE = "remote-base"


def test_local_create_object_passthrough(platform: DatacloudPlatform) -> None:
    """LOCAL base create_object passes through to the LOCAL ontology backend."""
    onto_local, *_ = platform._fakes  # type: ignore[attr-defined]
    obj_data: dict[str, str] = {"object_code": "obj1", "object_name": "Test"}
    result = platform.create_object(LOCAL, "scene1", obj_data)
    assert result == obj_data
    assert len(onto_local._created_objects) == 1  # type: ignore[attr-defined]
    assert onto_local._created_objects[0] == (LOCAL, "scene1", obj_data)  # type: ignore[attr-defined]


def test_remote_create_object_permission_error(platform: DatacloudPlatform) -> None:
    """REMOTE base create_object raises PermissionError because the backend is readonly."""
    obj_data: dict[str, str] = {"object_code": "obj1", "object_name": "Test"}
    with pytest.raises(PermissionError, match="read-only"):
        platform.create_object(REMOTE, "scene1", obj_data)


def test_local_search_routes_to_knowledge(platform: DatacloudPlatform) -> None:
    """LOCAL base search() routes through FakeKnowledgeBackend."""
    _, _, know, *_ = platform._fakes  # type: ignore[attr-defined]
    candidate = MatchCandidate(
        term_id="t1",
        term_name="test",
        term_type_code="metric",
        match_type="semantic",
        confidence=0.9,
        score=0.9,
    )
    know.candidates = [candidate]
    result = MatchResult(exact={"test": (candidate,)}, fuzzy={})
    know._disambiguated = [result]

    results = platform.search(LOCAL, "test")
    assert len(results) == 1
    assert results[0] == result


def test_remote_search_falls_back_to_default(platform: DatacloudPlatform) -> None:
    """REMOTE base search uses the default knowledge backend when the preset
    does not cover knowledge."""
    # Re-register REMOTE preset *without* knowledge so it falls back to default
    register_preset(
        "REMOTE",
        {
            "ontology": "remote-http",
            "execution": "none",
            "storage": "none",
        },
    )
    # Clear the platform's backend cache to pick up new resolution
    platform._backend_cache.clear()

    _, _, know, *_ = platform._fakes  # type: ignore[attr-defined]
    candidate = MatchCandidate(
        term_id="t2",
        term_name="remote_term",
        term_type_code="dimension",
        match_type="exact",
        confidence=1.0,
        score=1.0,
    )
    know.candidates = [candidate]
    result = MatchResult(exact={"remote_term": (candidate,)}, fuzzy={})
    know._disambiguated = [result]

    results = platform.search(REMOTE, "remote_term")
    assert len(results) == 1
    assert results[0] == result


def test_remote_execution_permission_error(platform: DatacloudPlatform) -> None:
    """REMOTE base execute_action raises PermissionError because execution=none."""
    with pytest.raises(PermissionError, match="Execution not available"):
        platform.execute_action(REMOTE, {"name": "test"}, context={})


def test_nonexistent_base_id_key_error(platform: DatacloudPlatform) -> None:
    """An unregistered base_id raises KeyError."""
    with pytest.raises(KeyError, match="not found"):
        platform.create_object("no-such-base", "scene1", {})


def test_manual_backends_fine_grained_override(platform: DatacloudPlatform) -> None:
    """manual_backends={'execution': 'none'} on a LOCAL base overrides the
    preset default, making execute_action raise PermissionError."""
    from datacloud_platform import OntologyBaseEntry

    entry = OntologyBaseEntry(
        base_id="local-noexec",
        display_name="无执行库",
        source_type="LOCAL",
        manual_backends={"execution": "none"},
    )
    platform.create_base(entry)

    with pytest.raises(PermissionError, match="Execution not available"):
        platform.execute_action("local-noexec", {"name": "test"}, context={})


def test_two_local_bases_share_ontology_instance(platform: DatacloudPlatform) -> None:
    """Two LOCAL bases use the same ontology backend instance."""
    onto_local, *_ = platform._fakes  # type: ignore[attr-defined]

    # Register a second LOCAL base
    from datacloud_platform import OntologyBaseEntry

    entry2 = OntologyBaseEntry(
        base_id="local-base-2",
        display_name="本地库2",
        source_type="LOCAL",
    )
    platform.create_base(entry2)

    # Both bases resolve to the same "fake-data" ontology implementation
    backend1 = platform._ontology_for(LOCAL)
    backend2 = platform._ontology_for("local-base-2")
    assert backend1 is backend2
    assert backend1 is onto_local
