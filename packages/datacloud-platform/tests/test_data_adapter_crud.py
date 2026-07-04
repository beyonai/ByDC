"""Regression tests for DataCloudDataBackend — Phase 4 CRUD + Phase 5 cache API.

Tests create/update/delete object operations and the objects_registry.json
fast-path loading introduced in Phase 2.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from datacloud_platform.adapters.data_adapter import DataCloudDataBackend
from datacloud_platform.adapters.json_entity_store import JsonEntityStore


@pytest.fixture
def backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DataCloudDataBackend:
    """DataCloudDataBackend with _resolve_base_path redirected to tmp_path."""
    be = DataCloudDataBackend()

    # Override _resolve_base_path to use temp dir instead of /data/{base_id}
    def _resolve(base_id: str) -> Path:
        return tmp_path / base_id

    monkeypatch.setattr(be, "_resolve_base_path", _resolve)
    return be


@pytest.fixture
def entity_store(backend: DataCloudDataBackend) -> JsonEntityStore:
    """JsonEntityStore pointing at the backend's base path for 'test-base'."""
    base_path = backend._resolve_base_path("test-base")  # noqa: SLF001
    return JsonEntityStore(base_path)


class TestCreateObject:
    def test_create_object_no_permission_error(
        self, backend: DataCloudDataBackend
    ) -> None:
        """create_object should succeed without PermissionError (Phase 4)."""
        obj = {"object_code": "test_obj", "object_name": "Test Object"}
        result = backend.create_object("test-base", obj)
        assert result["object_code"] == "test_obj"
        assert result["object_name"] == "Test Object"

    def test_create_object_persists_to_store(
        self, backend: DataCloudDataBackend, entity_store: JsonEntityStore
    ) -> None:
        obj = {"object_code": "order", "object_name": "Order"}
        backend.create_object("test-base", obj)
        # Verify via JsonEntityStore
        saved = entity_store.get("objects", "order")
        assert saved is not None
        assert saved["object_code"] == "order"

    def test_create_object_rebuilds_index(
        self, backend: DataCloudDataBackend, entity_store: JsonEntityStore
    ) -> None:
        """create_object should rebuild and persist the index."""
        backend.create_object(
            "test-base", {"object_code": "prod", "object_name": "Product"}
        )
        idx = entity_store.load_index("objects")
        assert "prod" in idx

    def test_create_object_requires_code(self, backend: DataCloudDataBackend) -> None:
        """Missing object_code should raise ValueError."""
        with pytest.raises(ValueError, match="object_code is required"):
            backend.create_object("test-base", {"object_name": "No Code"})


class TestUpdateObject:
    def test_update_object(
        self, backend: DataCloudDataBackend, entity_store: JsonEntityStore
    ) -> None:
        """Update an existing object."""
        backend.create_object(
            "test-base", {"object_code": "prod", "object_name": "Product"}
        )
        updated = backend.update_object(
            "test-base",
            "prod",
            {"object_code": "prod", "object_name": "Updated Product"},
        )
        assert updated["object_name"] == "Updated Product"
        saved = entity_store.get("objects", "prod")
        assert saved is not None
        assert saved["object_name"] == "Updated Product"

    def test_update_object_rebuilds_index(
        self, backend: DataCloudDataBackend, entity_store: JsonEntityStore
    ) -> None:
        backend.create_object("test-base", {"object_code": "sku", "object_name": "SKU"})
        backend.update_object(
            "test-base", "sku", {"object_code": "sku", "object_name": "New SKU"}
        )
        idx = entity_store.load_index("objects")
        assert idx["sku"]["name"] == "New SKU"


class TestDeleteObject:
    def test_delete_object(
        self, backend: DataCloudDataBackend, entity_store: JsonEntityStore
    ) -> None:
        """Delete an existing object."""
        backend.create_object(
            "test-base", {"object_code": "tmp", "object_name": "Temp"}
        )
        backend.delete_object("test-base", "tmp")
        assert entity_store.get("objects", "tmp") is None

    def test_delete_object_rebuilds_index(
        self, backend: DataCloudDataBackend, entity_store: JsonEntityStore
    ) -> None:
        backend.create_object("test-base", {"object_code": "bye", "object_name": "Bye"})
        backend.delete_object("test-base", "bye")
        idx = entity_store.load_index("objects")
        assert "bye" not in idx

    def test_delete_nonexistent_no_error(self, backend: DataCloudDataBackend) -> None:
        """Delete on nonexistent object should not raise."""
        backend.delete_object("test-base", "nonexistent")


class TestLoadOntologyFastPath:
    def test_registry_file_is_written(self, backend: DataCloudDataBackend) -> None:
        """batch_import_ontology writes objects_registry.json."""
        from datacloud_platform.models import ParsedOwlContent

        parsed = ParsedOwlContent(
            objects=[
                {"object_code": "a", "object_name": "Alpha"},
                {"object_code": "b", "object_name": "Bravo"},
            ],
            views=[],
            relations=[],
        )
        base_path = backend._resolve_base_path("test-base")  # noqa: SLF001
        counts = backend.batch_import_ontology(
            base_path,
            parsed.objects,
            parsed.views,
            parsed.relations,
            parsed.actions,
            parsed.dbsources,
        )
        assert counts["objects"] == 2
        registry_path = base_path / "objects_registry.json"
        assert registry_path.exists()

        content = json.loads(registry_path.read_text(encoding="utf-8"))
        assert len(content["objects"]) == 2

    def test_load_ontology_fast_path_performance(
        self, backend: DataCloudDataBackend
    ) -> None:
        """load_ontology with objects_registry.json should complete in < 2s."""
        try:
            from datacloud_data_sdk.ontology.loader import OntologyLoader  # noqa: F401
        except ImportError:
            pytest.skip("datacloud_data_sdk not available")

        from datacloud_platform.models import ParsedOwlContent

        parsed = ParsedOwlContent(
            objects=[
                {"object_code": f"obj{i}", "object_name": f"Object {i}"}
                for i in range(100)
            ],
            views=[],
            relations=[],
        )
        base_path = backend._resolve_base_path("fast-test")  # noqa: SLF001
        backend.batch_import_ontology(
            base_path,
            parsed.objects,
            parsed.views,
            parsed.relations,
            parsed.actions,
            parsed.dbsources,
        )

        start = time.monotonic()
        loader = backend.load_ontology(base_path)
        elapsed = time.monotonic() - start

        assert elapsed < 2.0, f"load_ontology took {elapsed:.3f}s, expected < 2.0s"
        # Verify loader has the objects
        assert len(loader._classes) == 100  # type: ignore[union-attr]  # noqa: SLF001


class TestSaveParsedContent:
    def test_batch_import_ontology_creates_shard_files(
        self, backend: DataCloudDataBackend, entity_store: JsonEntityStore
    ) -> None:
        """batch_import_ontology writes per-object .json files in shard directories."""
        from datacloud_platform.models import ParsedOwlContent

        parsed = ParsedOwlContent(
            objects=[{"object_code": "order", "object_name": "Order"}],
            views=[{"view_code": "v_order", "view_name": "View Order"}],
            relations=[
                {
                    "relation_code": "r1",
                    "source_class": "order",
                    "target_class": "order",
                }
            ],
        )
        base_path = backend._resolve_base_path("test-base")  # noqa: SLF001
        counts = backend.batch_import_ontology(
            base_path,
            parsed.objects,
            parsed.views,
            parsed.relations,
            parsed.actions,
            parsed.dbsources,
        )

        assert counts["objects"] == 1
        assert counts["views"] == 1
        assert counts["relations"] == 1

        # Verify shard files exist
        assert entity_store.get("objects", "order") is not None
        assert entity_store.get("views", "v_order") is not None
        assert entity_store.get("relations", "r1") is not None

    def test_batch_import_ontology_rebuilds_all_indexes(
        self, backend: DataCloudDataBackend
    ) -> None:
        """All three entity-type indexes are rebuilt after batch_import_ontology."""
        from datacloud_platform.models import ParsedOwlContent

        parsed = ParsedOwlContent(
            objects=[{"object_code": "o1", "object_name": "O1"}],
            views=[{"view_code": "v1", "view_name": "V1"}],
            relations=[
                {"relation_code": "r1", "source_class": "o1", "target_class": "o1"}
            ],
        )
        base_path = backend._resolve_base_path("test-base")  # noqa: SLF001
        backend.batch_import_ontology(
            base_path,
            parsed.objects,
            parsed.views,
            parsed.relations,
            parsed.actions,
            parsed.dbsources,
        )

        es = JsonEntityStore(base_path)
        for et in ("objects", "views", "relations"):
            idx = es.load_index(et)
            assert len(idx) == 1, f"Index for {et} should have 1 entry, got {len(idx)}"


class TestDatasourceCRUD:
    def test_create_datasource(
        self, backend: DataCloudDataBackend, entity_store: JsonEntityStore
    ) -> None:
        ds = {"db": [{"dbId": "mydb", "dbCode": "mydb"}]}
        result = backend.create_datasource("test-base", ds)
        assert result is not None
        saved = entity_store.get("datasources", "mydb")
        assert saved is not None

    def test_delete_datasource(
        self, backend: DataCloudDataBackend, entity_store: JsonEntityStore
    ) -> None:
        ds = {"db": [{"dbId": "tempdb", "dbCode": "tempdb"}]}
        backend.create_datasource("test-base", ds)
        backend.delete_datasource("test-base", "tempdb")
        assert entity_store.get("datasources", "tempdb") is None
