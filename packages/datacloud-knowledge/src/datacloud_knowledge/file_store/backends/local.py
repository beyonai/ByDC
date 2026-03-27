from __future__ import annotations

import contextlib
import json
import tempfile
from pathlib import Path
from typing import Any, BinaryIO

from datacloud_knowledge.file_store.errors import FileNotFoundInStoreError
from datacloud_knowledge.file_store.types import JsonDict, PutOutcome


def _shard(md5: str) -> tuple[str, str]:
    return md5[:2], md5[2:4]


def _safe_directory(directory: str) -> str:
    directory = directory.strip().strip("/")
    directory = directory.replace("\\", "/")
    parts = [p for p in directory.split("/") if p and p not in [".", ".."]]
    return "/".join(parts) if parts else "default"


class LocalFileBackend:
    def __init__(self, root_dir: str):
        self.root_dir = Path(root_dir)

    def exists(self, md5: str) -> bool:
        return self._index_path(md5).exists()

    def put(self, directory: str, md5: str, stream: BinaryIO, meta: JsonDict) -> PutOutcome:
        directory = _safe_directory(directory)

        index_path = self._index_path(md5)
        if index_path.exists():
            index = self._read_json(index_path)
            canonical = str(index["canonical_directory"])
            if directory != canonical:
                self._write_ref(directory=directory, md5=md5, canonical_directory=canonical)
            return PutOutcome(wrote_content=False, canonical_directory=canonical)

        # First time: write content under this directory (canonical)
        content_path = self._content_path(directory=directory, md5=md5)
        content_path.parent.mkdir(parents=True, exist_ok=True)

        tmp_file: str | None = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, dir=str(content_path.parent)) as f:
                tmp_file = f.name
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)

            Path(tmp_file).replace(content_path)
            tmp_file = None
        finally:
            if tmp_file:
                with contextlib.suppress(OSError):
                    Path(tmp_file).unlink()

        index_path.parent.mkdir(parents=True, exist_ok=True)
        idx: JsonDict = {
            "canonical_directory": directory,
            "meta": {**meta, "directory": directory},
        }
        self._write_json_atomic(index_path, idx)
        return PutOutcome(wrote_content=True, canonical_directory=directory)

    def get(self, md5: str) -> tuple[BinaryIO, JsonDict]:
        index = self._read_index(md5)
        directory = str(index["canonical_directory"])
        meta = dict(index["meta"])
        content_path = self._content_path(directory=directory, md5=md5)
        if not content_path.exists():
            raise FileNotFoundInStoreError(md5)
        return content_path.open("rb"), meta

    def get_meta(self, md5: str) -> JsonDict:
        index = self._read_index(md5)
        return dict(index["meta"])

    # ---- paths & json helpers ----

    def _index_path(self, md5: str) -> Path:
        aa, bb = _shard(md5)
        return self.root_dir / "index" / aa / bb / f"{md5}.json"

    def _content_path(self, directory: str, md5: str) -> Path:
        aa, bb = _shard(md5)
        return self.root_dir / directory / "objects" / aa / bb / md5

    def _ref_path(self, directory: str, md5: str) -> Path:
        aa, bb = _shard(md5)
        return self.root_dir / directory / "refs" / aa / bb / f"{md5}.json"

    def _write_ref(self, directory: str, md5: str, canonical_directory: str) -> None:
        ref_path = self._ref_path(directory=directory, md5=md5)
        ref_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_json_atomic(ref_path, {"canonical_directory": canonical_directory})

    def _read_index(self, md5: str) -> JsonDict:
        index_path = self._index_path(md5)
        if not index_path.exists():
            raise FileNotFoundInStoreError(md5)
        return self._read_json(index_path)

    def _read_json(self, path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)  # type: ignore[no-any-return]

    def _write_json_atomic(self, path: Path, obj: JsonDict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", delete=False, dir=str(path.parent), encoding="utf-8"
            ) as f:
                tmp = f.name
                json.dump(obj, f, ensure_ascii=False, indent=2)
            Path(tmp).replace(path)
            tmp = None
        finally:
            if tmp:
                with contextlib.suppress(OSError):
                    Path(tmp).unlink()
