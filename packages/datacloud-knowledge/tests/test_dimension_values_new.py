"""DimensionValueResolver unit tests — resolve_value_to_property / get_referenced_by.

Uses unittest.mock to replace create_reader() with a controllable FakeDimValueReader.
"""

from __future__ import annotations

import contextlib
from collections.abc import Generator
from typing import TYPE_CHECKING
from unittest.mock import patch as _patch

import pytest
from datacloud_knowledge.retrieval.dimension_values import DimensionValueResolver

if TYPE_CHECKING:
    pass


class FakeDimValueReader:
    """Fake reader implementing the _DimValueReader protocol.

    Implements get_relation_target_ids / get_terms_batch_raw
    for testing resolve_value_to_property / get_referenced_by.
    """

    def __init__(self) -> None:
        self._terms: dict[str, dict[str, str | None]] = {}
        self._relations: dict[str, list[str]] = {}  # target_term_ids -> source_term_ids

    def seed_term(
        self,
        term_id: str,
        *,
        term_code: str = "",
        term_name: str = "",
        parent_term_id: str | None = None,
    ) -> FakeDimValueReader:
        """Register a term."""
        self._terms[term_id] = {
            "term_id": term_id,
            "term_code": term_code,
            "term_name": term_name,
            "parent_term_id": parent_term_id,
        }
        return self

    def seed_relation(
        self,
        *,
        source_term_ids: list[str],
        target_term_ids: list[str],
    ) -> FakeDimValueReader:
        """Register a relation: which sources reference which targets."""
        for tid in target_term_ids:
            self._relations.setdefault(tid, []).extend(source_term_ids)
        return self

    def get_relation_target_ids(
        self,
        *,
        source_term_ids: list[str] | None = None,
        target_term_ids: list[str] | None = None,
        relation_category: str | None = None,
    ) -> list[str]:
        """Return source term_ids that reference the given targets."""
        _ = (source_term_ids, relation_category)
        result: list[str] = []
        if target_term_ids:
            for tid in target_term_ids:
                result.extend(self._relations.get(tid, []))
        return result

    def get_terms_batch_raw(
        self,
        *,
        term_ids: list[str] | None = None,
        term_codes: list[str] | None = None,
    ) -> list[dict[str, str | None]]:
        """Batch return term dicts."""
        _ = term_codes
        result: list[dict[str, str | None]] = []
        if term_ids:
            for tid in term_ids:
                if tid in self._terms:
                    result.append(self._terms[tid])
        return result


@pytest.fixture(autouse=True)
def _reset_dimension_resolver() -> None:
    """Reset DimensionValueResolver singleton before each test."""
    DimensionValueResolver.reset()


@pytest.fixture
def resolver() -> DimensionValueResolver:
    """Return a fresh DimensionValueResolver instance."""
    return DimensionValueResolver()


@contextlib.contextmanager
def _patch_reader(fake: FakeDimValueReader) -> Generator[None, None, None]:
    """Context manager: patch create_reader to return the fake reader."""
    with _patch(
        "datacloud_knowledge.retrieval.dimension_values.create_reader",
        return_value=fake,
    ):
        yield


# -- resolve_value_to_property -------------------------------------------------


class TestResolveValueToProperty:
    """resolve_value_to_property() -- value term -> property + object."""

    @pytest.fixture
    def fake_reader(self) -> FakeDimValueReader:
        """Build a fake reader with a complete chain.

        chain: value -> type_root -> (up) prop -> object
        """
        return (
            FakeDimValueReader()
            # value term
            .seed_term("val-1", term_code="LEADER", parent_term_id="type-root-1")
            # type_root (value's parent)
            .seed_term(
                "type-root-1", term_code="enterprise_level_type", term_name="enterprise_level_type"
            )
            # HAS_TERM: prop_id -> type_root
            .seed_relation(source_term_ids=["prop-1"], target_term_ids=["type-root-1"])
            # property
            .seed_term(
                "prop-1",
                term_code="enterprise_level",
                term_name="enterprise_level",
                parent_term_id="obj-1",
            )
            # object
            .seed_term("obj-1", term_code="enterprise", term_name="enterprise")
        )

    def test_resolves_full_chain(
        self, resolver: DimensionValueResolver, fake_reader: FakeDimValueReader
    ) -> None:
        """Full chain: value -> type_root -> prop -> object."""
        with _patch_reader(fake_reader):
            result = resolver.resolve_value_to_property("val-1")

        assert result == {
            "propertyCode": "enterprise_level",
            "objectCode": "enterprise",
        }

    def test_empty_value_term_id_returns_empty_dict(self, resolver: DimensionValueResolver) -> None:
        """Empty value_term_id returns empty dict immediately."""
        result = resolver.resolve_value_to_property("")
        assert result == {}

    def test_unknown_value_term_returns_empty_dict(self, resolver: DimensionValueResolver) -> None:
        """Non-existent value_term_id returns empty dict."""
        fake = FakeDimValueReader()
        with _patch_reader(fake):
            result = resolver.resolve_value_to_property("no-such")
        assert result == {}

    def test_value_without_parent_returns_empty_dict(
        self, resolver: DimensionValueResolver
    ) -> None:
        """Value without parent_term_id returns empty dict."""
        fake = FakeDimValueReader().seed_term("orphan", term_code="orphan")
        with _patch_reader(fake):
            result = resolver.resolve_value_to_property("orphan")
        assert result == {}

    def test_type_root_without_referencing_prop_returns_empty_dict(
        self, resolver: DimensionValueResolver
    ) -> None:
        """type_root with no HAS_TERM references returns empty dict."""
        fake = (
            FakeDimValueReader()
            .seed_term("val-1", term_code="X", parent_term_id="type-root-1")
            .seed_term("type-root-1", term_code="type_x")
        )
        with _patch_reader(fake):
            result = resolver.resolve_value_to_property("val-1")
        assert result == {}

    def test_prop_without_object_parent_returns_empty_dict(
        self, resolver: DimensionValueResolver
    ) -> None:
        """Prop without parent (object) returns empty dict (no object_id -> early return)."""
        fake = (
            FakeDimValueReader()
            .seed_term("val-1", term_code="X", parent_term_id="type-root-1")
            .seed_term("type-root-1", term_code="type_x")
            .seed_relation(source_term_ids=["prop-1"], target_term_ids=["type-root-1"])
            .seed_term("prop-1", term_code="prop_x", term_name="prop_x")
        )
        with _patch_reader(fake):
            result = resolver.resolve_value_to_property("val-1")
        assert result == {}


# -- get_referenced_by --------------------------------------------------------


class TestGetReferencedBy:
    """get_referenced_by() -- find all properties referencing a value type."""

    @pytest.fixture
    def multi_prop_reader(self) -> FakeDimValueReader:
        """Build a fake reader with multiple properties referencing the same type."""
        return (
            FakeDimValueReader()
            # value term
            .seed_term("val-1", term_code="LEADER", parent_term_id="type-root-1")
            # type_root
            .seed_term(
                "type-root-1", term_code="enterprise_level_type", term_name="enterprise_level_type"
            )
            # two props reference the same type_root
            .seed_relation(
                source_term_ids=["prop-1", "prop-2"],
                target_term_ids=["type-root-1"],
            )
            # prop-1 -> object-1
            .seed_term(
                "prop-1",
                term_code="enterprise_level",
                term_name="enterprise_level",
                parent_term_id="obj-1",
            )
            # prop-2 -> object-2
            .seed_term(
                "prop-2",
                term_code="supplier_level",
                term_name="supplier_level",
                parent_term_id="obj-2",
            )
            # objects
            .seed_term("obj-1", term_code="enterprise", term_name="enterprise")
            .seed_term("obj-2", term_code="supplier", term_name="supplier")
        )

    def test_returns_all_referencing_properties(
        self, resolver: DimensionValueResolver, multi_prop_reader: FakeDimValueReader
    ) -> None:
        """Returns all properties + objects referencing this value type."""
        with _patch_reader(multi_prop_reader):
            results = resolver.get_referenced_by("val-1")

        assert len(results) == 2
        # order-independent checks
        codes = {(r["objectCode"], r["propertyCode"]) for r in results}
        assert ("enterprise", "enterprise_level") in codes
        assert ("supplier", "supplier_level") in codes

        names = {(r["objectName"], r["propertyName"]) for r in results}
        assert ("enterprise", "enterprise_level") in names
        assert ("supplier", "supplier_level") in names

    def test_empty_value_term_id_returns_empty_list(self, resolver: DimensionValueResolver) -> None:
        """Empty value_term_id returns empty list."""
        results = resolver.get_referenced_by("")
        assert results == []

    def test_unknown_value_term_returns_empty_list(self, resolver: DimensionValueResolver) -> None:
        """Non-existent value_term_id returns empty list."""
        fake = FakeDimValueReader()
        with _patch_reader(fake):
            results = resolver.get_referenced_by("no-such")
        assert results == []

    def test_no_referencing_props_returns_empty_list(
        self, resolver: DimensionValueResolver
    ) -> None:
        """No property references the type -> empty list."""
        fake = (
            FakeDimValueReader()
            .seed_term("val-1", term_code="X", parent_term_id="type-root-1")
            .seed_term("type-root-1", term_code="type_x")
        )
        with _patch_reader(fake):
            results = resolver.get_referenced_by("val-1")
        assert results == []
