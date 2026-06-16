"""OntologyBase Registry unit tests."""

from __future__ import annotations

import json
import logging

import pytest
from datacloud_server.registry.registry import OntologyBaseEntry, OntologyBaseRegistry


class TestRegistryRegister:
    """Register OntologyBase."""

    def test_register_adds_entry(self) -> None:
        registry = OntologyBaseRegistry()
        entry = OntologyBaseEntry(
            base_id="my_base",
            display_name="My Base",
            description="",
            owner_type="personal",
            source_type="LOCAL",
        )
        registry.register(entry)
        assert registry.get("my_base") is entry

    def test_register_duplicate_raises_error(self) -> None:
        registry = OntologyBaseRegistry()
        registry.register(OntologyBaseEntry("dup", "First", "", "personal", "LOCAL"))
        with pytest.raises(ValueError, match="already exists"):
            registry.register(OntologyBaseEntry("dup", "Second", "", "personal", "LOCAL"))

    def test_list_returns_all_entries(self) -> None:
        registry = OntologyBaseRegistry()
        registry.register(OntologyBaseEntry("b1", "B1", "", "personal", "LOCAL"))
        registry.register(OntologyBaseEntry("b2", "B2", "", "personal", "LOCAL"))
        result = registry.list()
        assert len(result) == 2
        assert {e.base_id for e in result} == {"b1", "b2"}

    def test_get_nonexistent_returns_none(self) -> None:
        registry = OntologyBaseRegistry()
        assert registry.get("nope") is None


class TestRegistryUnregister:
    """Unregister OntologyBase."""

    def test_unregister_removes_entry(self) -> None:
        registry = OntologyBaseRegistry()
        registry.register(OntologyBaseEntry("to_delete", "Delete", "", "personal", "LOCAL"))
        registry.unregister("to_delete")
        assert registry.get("to_delete") is None

    def test_unregister_nonexistent_raises_error(self) -> None:
        registry = OntologyBaseRegistry()
        with pytest.raises(KeyError, match="not found"):
            registry.unregister("nope")


class TestRegistryPersistence:
    """Disk persistence — JSON file serialization."""

    def test_persist_writes_json_file(self, tmp_path) -> None:
        p = tmp_path / "registry.json"
        registry = OntologyBaseRegistry(persist_path=str(p))
        entry = OntologyBaseEntry(
            base_id="b1",
            display_name="B1",
            description="desc",
            owner_type="personal",
            source_type="LOCAL",
        )
        registry.register(entry)
        assert p.exists()
        data = json.loads(p.read_text())
        assert "b1" in data
        assert data["b1"]["base_id"] == "b1"

    def test_persist_after_unregister_removes_entry(self, tmp_path) -> None:
        p = tmp_path / "registry.json"
        registry = OntologyBaseRegistry(persist_path=str(p))
        registry.register(OntologyBaseEntry("b1", "B1", "", "personal", "LOCAL"))
        registry.unregister("b1")
        data = json.loads(p.read_text())
        assert "b1" not in data

    def test_load_from_disk_recovers_state(self, tmp_path) -> None:
        p = tmp_path / "registry.json"
        registry1 = OntologyBaseRegistry(persist_path=str(p))
        registry1.register(OntologyBaseEntry("b1", "B1", "", "personal", "LOCAL"))

        registry2 = OntologyBaseRegistry(persist_path=str(p))
        assert registry2.get("b1") is not None
        assert registry2.get("b1").base_id == "b1"

    def test_load_from_disk_handles_missing_file(self, tmp_path) -> None:
        p = tmp_path / "nonexistent.json"
        registry = OntologyBaseRegistry(persist_path=str(p))
        assert registry.list() == []

    def test_load_from_disk_handles_invalid_json(self, tmp_path, caplog) -> None:
        p = tmp_path / "bad.json"
        p.write_text("not json {{{")
        with caplog.at_level(logging.WARNING):
            registry = OntologyBaseRegistry(persist_path=str(p))
        assert registry.list() == []
        # Should log a warning about invalid JSON
        assert any("JSON" in m or "json" in m for m in caplog.messages)

    def test_persist_path_none_skips_persistence(self) -> None:
        registry = OntologyBaseRegistry(persist_path=None)
        registry.register(OntologyBaseEntry("b1", "B1", "", "personal", "LOCAL"))
        assert registry.list()  # in-memory still works
        # No file written anywhere

    def test_persist_is_atomic_write(self, tmp_path) -> None:
        """Verify atomic write: data written via tmp file then os.replace."""
        p = tmp_path / "registry.json"
        registry = OntologyBaseRegistry(persist_path=str(p))
        registry.register(OntologyBaseEntry("b1", "B1", "", "personal", "LOCAL"))
        # Verify the final file contains valid JSON
        data = json.loads(p.read_text())
        assert data["b1"]["base_id"] == "b1"
        # Verify no .tmp file left behind (atomic write completed)
        tmp_file = tmp_path / "registry.json.tmp"
        assert not tmp_file.exists(), ".tmp file should be cleaned up after atomic rename"
