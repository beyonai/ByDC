"""Type4: tests for knowledge resource readiness and ingest prerequisites."""

from __future__ import annotations

import pytest


@pytest.mark.type4_knowledge
def test_knowledge_dirs_exist(resource_knowledge_dir) -> None:
    assert resource_knowledge_dir.exists()
    assert (resource_knowledge_dir / "ontology").exists()
    assert (resource_knowledge_dir / "terminology").exists()


@pytest.mark.type4_knowledge
def test_ontology_registry_exists(resource_knowledge_dir) -> None:
    registry = resource_knowledge_dir / "ontology" / "modules" / "objects_registry.json"
    assert registry.exists()


@pytest.mark.type4_knowledge
def test_terminology_core_files_exist(resource_knowledge_dir) -> None:
    term_dir = resource_knowledge_dir / "terminology"
    required = ["domain.csv", "term.csv", "term_type.csv", "term_relation.csv"]
    for file_name in required:
        assert (term_dir / file_name).exists(), f"missing terminology file: {file_name}"
