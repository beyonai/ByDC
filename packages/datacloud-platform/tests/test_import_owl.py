"""Regression tests for OWL import flow — Phase 2+5 unified registry + shard output.

Verifies that OWL import writes objects_registry.json, creates sharded entity
files, and does not use hardcoded /tmp paths.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from datacloud_platform.adapters.data_adapter import DataCloudDataBackend
from datacloud_platform.adapters.json_entity_store import JsonEntityStore
from datacloud_platform.models import ParsedOwlContent


@pytest.fixture
def backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DataCloudDataBackend:
    """DataCloudDataBackend with _resolve_base_path redirected to tmp_path."""
    be = DataCloudDataBackend()

    def _resolve(base_id: str) -> Path:
        return tmp_path / base_id

    monkeypatch.setattr(be, "_resolve_base_path", _resolve)
    return be


@pytest.fixture
def parsed_owl() -> ParsedOwlContent:
    """Realistic ParsedOwlContent simulating OWL parse output."""
    return ParsedOwlContent(
        objects=[
            {"object_code": "order", "object_name": "Order", "source_type": "TABLE"},
            {
                "object_code": "product",
                "object_name": "Product",
                "source_type": "TABLE",
            },
            {
                "object_code": "customer",
                "object_name": "Customer",
                "source_type": "VIEW",
            },
        ],
        views=[
            {
                "view_code": "v_order_detail",
                "view_name": "Order Detail View",
                "objects": ["order"],
            },
        ],
        relations=[
            {
                "relation_code": "order_to_product",
                "relation_name": "Order → Product",
                "source_class": "order",
                "target_class": "product",
                "relation_type": "MANY_TO_ONE",
            },
        ],
    )


class TestImportOwlWritesRegistry:
    def test_registry_json_exists(
        self, backend: DataCloudDataBackend, parsed_owl: ParsedOwlContent
    ) -> None:
        """OWL import must generate objects_registry.json in the base path."""
        base_path = backend._resolve_base_path("import-test")  # noqa: SLF001
        backend.save_parsed_content(base_path, parsed_owl)

        registry = base_path / "objects_registry.json"
        assert registry.exists(), f"Expected {registry} to be created"

    def test_registry_json_contains_all_types(
        self, backend: DataCloudDataBackend, parsed_owl: ParsedOwlContent
    ) -> None:
        """objects_registry.json must contain objects, views, and relations keys."""
        base_path = backend._resolve_base_path("import-test")  # noqa: SLF001
        backend.save_parsed_content(base_path, parsed_owl)

        registry = base_path / "objects_registry.json"
        content = json.loads(registry.read_text(encoding="utf-8"))
        assert "objects" in content
        assert "views" in content
        assert "relations" in content
        assert len(content["objects"]) == 3
        assert len(content["views"]) == 1
        assert len(content["relations"]) == 1

    def test_registry_json_is_valid_json(
        self, backend: DataCloudDataBackend, parsed_owl: ParsedOwlContent
    ) -> None:
        """The registry file must be valid, parseable JSON."""
        base_path = backend._resolve_base_path("import-test")  # noqa: SLF001
        backend.save_parsed_content(base_path, parsed_owl)

        registry = base_path / "objects_registry.json"
        content = json.loads(registry.read_text(encoding="utf-8"))
        assert isinstance(content, dict)
        for key in ("objects", "views", "relations"):
            assert isinstance(content[key], list), f"{key} should be a list"


class TestImportOwlCreatesShardedFiles:
    def test_sharded_object_files_exist(
        self, backend: DataCloudDataBackend, parsed_owl: ParsedOwlContent
    ) -> None:
        """Each object should have a shard file: objects/{shard}/{code}.json."""
        base_path = backend._resolve_base_path("import-test")  # noqa: SLF001
        backend.save_parsed_content(base_path, parsed_owl)

        for code in ("order", "product", "customer"):
            shard = code[:2].lower()
            entity_file = base_path / "objects" / shard / f"{code}.json"
            assert entity_file.exists(), f"Expected shard file {entity_file}"

    def test_sharded_view_files_exist(
        self, backend: DataCloudDataBackend, parsed_owl: ParsedOwlContent
    ) -> None:
        """Views should also be sharded under views/{shard}/{code}.json."""
        base_path = backend._resolve_base_path("import-test")  # noqa: SLF001
        backend.save_parsed_content(base_path, parsed_owl)

        v_code = "v_order_detail"
        shard = v_code[:2].lower()
        view_file = base_path / "views" / shard / f"{v_code}.json"
        assert view_file.exists(), f"Expected view file {view_file}"

    def test_sharded_relation_files_exist(
        self, backend: DataCloudDataBackend, parsed_owl: ParsedOwlContent
    ) -> None:
        """Relations should be sharded under relations/{shard}/{code}.json."""
        base_path = backend._resolve_base_path("import-test")  # noqa: SLF001
        backend.save_parsed_content(base_path, parsed_owl)

        r_code = "order_to_product"
        shard = r_code[:2].lower()
        rel_file = base_path / "relations" / shard / f"{r_code}.json"
        assert rel_file.exists(), f"Expected relation file {rel_file}"

    def test_shard_files_contain_correct_data(
        self, backend: DataCloudDataBackend, parsed_owl: ParsedOwlContent
    ) -> None:
        """Shard .json files contain the original entity data."""
        base_path = backend._resolve_base_path("import-test")  # noqa: SLF001
        backend.save_parsed_content(base_path, parsed_owl)

        es = JsonEntityStore(base_path)
        order = es.get("objects", "order")
        assert order is not None
        assert order["object_code"] == "order"
        assert order["object_name"] == "Order"
        assert order.get("source_type") == "TABLE"

    def test_index_files_are_rebuilt(
        self, backend: DataCloudDataBackend, parsed_owl: ParsedOwlContent
    ) -> None:
        """All entity-type _index.json files are rebuilt after import."""
        base_path = backend._resolve_base_path("import-test")  # noqa: SLF001
        backend.save_parsed_content(base_path, parsed_owl)

        for et in ("objects", "views", "relations"):
            index_path = base_path / et / "_index.json"
            assert index_path.exists(), f"Expected index {index_path}"
            content = json.loads(index_path.read_text(encoding="utf-8"))
            assert isinstance(content, dict)


class TestImportOwlNoHardcodedTmp:
    def test_save_parsed_content_uses_no_hardcoded_tmp(
        self, backend: DataCloudDataBackend, parsed_owl: ParsedOwlContent
    ) -> None:
        """save_parsed_content writes directly into the base_path, no /tmp dependency.

        We verify this indirectly: after save_parsed_content, /tmp should NOT
        contain any files related to this import under a hardcoded prefix.
        """
        base_path = backend._resolve_base_path("import-test")  # noqa: SLF001
        backend.save_parsed_content(base_path, parsed_owl)

        # The function should have written all output under base_path
        # Verify no owl_import_ residue in /tmp (best-effort check)
        tmp = Path("/tmp")
        if tmp.exists():
            owl_tmp_files = list(tmp.glob("owl_import_*"))
            assert len(owl_tmp_files) == 0, (
                f"Found hardcoded /tmp owl_import_ residue: {owl_tmp_files}"
            )


class TestImportOwlIdempotency:
    def test_double_import_overwrites(self, backend: DataCloudDataBackend) -> None:
        """Importing twice with different data overwrites existing files."""
        base_path = backend._resolve_base_path("import-test")  # noqa: SLF001

        parsed1 = ParsedOwlContent(
            objects=[{"object_code": "a", "object_name": "First"}],
            views=[],
            relations=[],
        )
        backend.save_parsed_content(base_path, parsed1)

        parsed2 = ParsedOwlContent(
            objects=[{"object_code": "a", "object_name": "Second"}],
            views=[],
            relations=[],
        )
        backend.save_parsed_content(base_path, parsed2)

        es = JsonEntityStore(base_path)
        a = es.get("objects", "a")
        assert a is not None
        assert a["object_name"] == "Second"

    def test_double_import_expands_objects(self, backend: DataCloudDataBackend) -> None:
        """Second import with new objects adds to the store without removing old."""
        base_path = backend._resolve_base_path("import-test")  # noqa: SLF001

        parsed1 = ParsedOwlContent(
            objects=[{"object_code": "a", "object_name": "Alpha"}],
            views=[],
            relations=[],
        )
        backend.save_parsed_content(base_path, parsed1)

        parsed2 = ParsedOwlContent(
            objects=[
                {"object_code": "a", "object_name": "Alpha v2"},
                {"object_code": "b", "object_name": "Bravo"},
            ],
            views=[],
            relations=[],
        )
        backend.save_parsed_content(base_path, parsed2)

        es = JsonEntityStore(base_path)
        assert es.get("objects", "a") is not None
        assert es.get("objects", "b") is not None
        assert es.get("objects", "a")["object_name"] == "Alpha v2"  # type: ignore[index]
