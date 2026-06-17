"""JSON Writer - atomic write + ensure_dir."""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003


class JSONWriter:
    """JSON file writer - atomic write (tmp -> rename)."""

    @staticmethod
    def ensure_dir(path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)

    def write_object(self, scene_path: Path, obj_data: dict) -> None:
        objects_dir = scene_path / "objects"
        self.ensure_dir(objects_dir)
        file_path = objects_dir / f"{obj_data['objectCode']}.json"
        self._atomic_write(file_path, obj_data)

    def write_view(self, scene_path: Path, view_data: dict) -> None:
        views_dir = scene_path / "views"
        self.ensure_dir(views_dir)
        view_code = view_data.get("viewCode", view_data.get("view_id", "unnamed"))
        file_path = views_dir / f"{view_code}.json"
        self._atomic_write(file_path, view_data)

    def write_relation(self, scene_path: Path, relations: list[dict]) -> None:
        self.ensure_dir(scene_path)
        file_path = scene_path / "relations.json"
        self._atomic_write(file_path, {"relations": relations})

    def delete_object(self, scene_path: Path, object_code: str) -> None:
        file_path = scene_path / "objects" / f"{object_code}.json"
        if file_path.exists():
            file_path.unlink()

    def delete_view(self, scene_path: Path, view_code: str) -> None:
        file_path = scene_path / "views" / f"{view_code}.json"
        if file_path.exists():
            file_path.unlink()

    @staticmethod
    def _atomic_write(file_path: Path, data: object) -> None:
        tmp_path = file_path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        tmp_path.replace(file_path)
