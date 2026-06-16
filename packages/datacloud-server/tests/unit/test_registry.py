"""OntologyBase Registry unit tests."""

from __future__ import annotations

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
