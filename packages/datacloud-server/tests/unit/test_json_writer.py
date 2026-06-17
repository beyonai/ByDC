"""JSON Writer unit tests - atomic write + ensure_dir."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003

from datacloud_server.storage.json_writer import JSONWriter


class TestJSONWriter:
    """JSON file atomic write tests."""

    def test_write_object_creates_file(self, tmp_path: Path) -> None:
        writer = JSONWriter()
        scene_path = tmp_path / "local_base" / "default"
        obj_data = {"objectCode": "product", "objectName": "Product"}

        writer.write_object(scene_path, obj_data)

        file_path = scene_path / "objects" / "product.json"
        assert file_path.exists()
        content = json.loads(file_path.read_text(encoding="utf-8"))
        assert content["objectCode"] == "product"

    def test_write_object_creates_parent_dirs(self, tmp_path: Path) -> None:
        writer = JSONWriter()
        scene_path = tmp_path / "new_base" / "new_scene"

        writer.write_object(scene_path, {"objectCode": "test", "objectName": "Test"})

        assert (scene_path / "objects").exists()

    def test_delete_object_removes_file(self, tmp_path: Path) -> None:
        writer = JSONWriter()
        scene_path = tmp_path / "base" / "scene"
        writer.write_object(scene_path, {"objectCode": "temp", "objectName": "Temp"})
        file_path = scene_path / "objects" / "temp.json"
        assert file_path.exists()

        writer.delete_object(scene_path, "temp")
        assert not file_path.exists()

    def test_delete_nonexistent_object_is_noop(self, tmp_path: Path) -> None:
        writer = JSONWriter()
        scene_path = tmp_path / "base" / "scene"
        writer.delete_object(scene_path, "no_such_object")

    def test_write_view_creates_file(self, tmp_path: Path) -> None:
        writer = JSONWriter()
        scene_path = tmp_path / "base" / "scene"
        view_data = {"viewCode": "analysis", "viewName": "Analysis View"}

        writer.write_view(scene_path, view_data)

        file_path = scene_path / "views" / "analysis.json"
        assert file_path.exists()

    def test_atomic_write_uses_tmp_then_rename(self, tmp_path: Path) -> None:
        writer = JSONWriter()
        scene_path = tmp_path / "base" / "scene"
        obj_data = {"objectCode": "atomic", "objectName": "Atomic"}

        writer.write_object(scene_path, obj_data)

        tmp_files = list(scene_path.glob("objects/*.tmp"))
        assert len(tmp_files) == 0

        final_path = scene_path / "objects" / "atomic.json"
        assert final_path.exists()
        content = json.loads(final_path.read_text(encoding="utf-8"))
        assert content["objectCode"] == "atomic"

    def test_write_relation_creates_file(self, tmp_path: Path) -> None:
        writer = JSONWriter()
        scene_path = tmp_path / "base" / "scene"
        relations = [
            {
                "relationCode": "r1",
                "sourceClass": "A",
                "targetClass": "B",
                "relationType": "MANY_TO_ONE",
            }
        ]

        writer.write_relation(scene_path, relations)

        file_path = scene_path / "relations.json"
        assert file_path.exists()
