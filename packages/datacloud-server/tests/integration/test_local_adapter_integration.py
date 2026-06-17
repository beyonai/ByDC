"""Integration tests for LocalOntologyAdapter using real OWL data.

Verifies OWL -> SDK -> adapter metadata read pipeline end-to-end.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from datacloud_server.adapters.local_adapter import LocalOntologyAdapter
from datacloud_server.models.object_type import ObjectType
from datacloud_server.storage.json_writer import JSONWriter


@pytest.fixture
def owl_data_dir(tmp_path: Path) -> Path:
    """Copy owl_example into tmp_path as a base directory."""
    src = Path("/workspace/projects/ontology_server/owl_example")
    dst = tmp_path / "owl_example"
    shutil.copytree(src, dst)
    # Return parent dir so adapter can address "owl_example" as baseId
    return tmp_path


@pytest.fixture
def adapter(owl_data_dir: Path) -> LocalOntologyAdapter:
    """Create LocalOntologyAdapter with data_dir = tmp_path (parent)."""
    writer = JSONWriter()
    return LocalOntologyAdapter(str(owl_data_dir), writer)


class TestOWLMetadataRead:
    """Metadata read operations using OWL data."""

    def test_list_scenes_returns_dirs(self, adapter: LocalOntologyAdapter) -> None:
        """OWL data has object/ and view/ directories as scenes."""
        scenes = adapter.list_scenes("owl_example")
        assert len(scenes) > 0
        scene_names = {s["sceneName"] for s in scenes}
        assert "object" in scene_names
        assert "view" in scene_names

    def test_get_objects_loads_all_objects(self, adapter: LocalOntologyAdapter) -> None:
        """All 8 objects loaded from OWL data."""
        objects = adapter.get_objects("owl_example", "object")
        assert len(objects) >= 8
        object_codes = {o["objectCode"] for o in objects}
        assert "by_customer" in object_codes
        assert "by_opportunity" in object_codes
        assert "by_project" in object_codes
        assert "by_rd_task" in object_codes

    def test_get_object_detail_has_fields(self, adapter: LocalOntologyAdapter) -> None:
        """Object detail includes fields and actions."""
        obj = adapter.get_object_detail("owl_example", "object", "by_customer")
        assert obj is not None
        assert obj["objectCode"] == "by_customer"
        assert obj["objectName"] == "客户信息表"
        assert len(obj["properties"]) >= 16
        assert len(obj["actions"]) >= 4

    def test_get_views_loads_all_views(self, adapter: LocalOntologyAdapter) -> None:
        """All 4 views loaded."""
        views = adapter.get_views("owl_example", "view")
        assert len(views) >= 4
        view_codes = {v["viewCode"] for v in views}
        assert "scene_sales_management" in view_codes
        assert "scene_crm_comprehensive_analysis" in view_codes

    def test_get_relations_returns_object_relations(self, adapter: LocalOntologyAdapter) -> None:
        """Relations between objects are loaded."""
        relations = adapter.get_relations("owl_example", "object")
        assert len(relations) >= 10
        assert len({r["relationCode"] for r in relations}) > 0

    def test_get_object_detail_nonexistent_returns_none(
        self, adapter: LocalOntologyAdapter
    ) -> None:
        """Non-existent object returns None."""
        obj = adapter.get_object_detail("owl_example", "object", "no_such_object")
        assert obj is None


class TestLocalAdapterCRUD:
    """CRUD operations with JSON persistence (no OWL dependency)."""

    @pytest.fixture
    def adapter(self, tmp_path: Path) -> LocalOntologyAdapter:
        writer = JSONWriter()
        return LocalOntologyAdapter(str(tmp_path), writer)

    def test_create_and_read_object(self, adapter: LocalOntologyAdapter) -> None:
        """Write object via JSON, then read back."""
        obj = ObjectType(
            object_code="product",
            object_name="Product",
            properties=[],  # extra=allow handles anything else in JSON
        )
        adapter.create_object("my_base", "default", obj)
        objects = adapter.get_objects("my_base", "default")
        assert len(objects) == 1
        assert objects[0]["objectCode"] == "product"

    def test_delete_object_removes_it(self, adapter: LocalOntologyAdapter) -> None:
        """Delete removes object from index."""
        adapter.create_object(
            "my_base",
            "default",
            ObjectType(object_code="temp", object_name="Temp"),
        )
        adapter.delete_object("my_base", "default", "temp")
        objects = adapter.get_objects("my_base", "default")
        assert len(objects) == 0

    def test_create_duplicate_raises_error(self, adapter: LocalOntologyAdapter) -> None:
        """Duplicate objectCode raises ValueError."""
        adapter.create_object(
            "my_base",
            "default",
            ObjectType(object_code="dup", object_name="Dup"),
        )
        with pytest.raises(ValueError, match="already exists"):
            adapter.create_object(
                "my_base",
                "default",
                ObjectType(object_code="dup", object_name="Dup"),
            )
