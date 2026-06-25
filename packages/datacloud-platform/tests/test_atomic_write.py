"""Regression tests for atomic_write_json — Phase 1 temp-file + atomic rename.

Tests normal write path, cleanup on error, and orphan tmp file reaping.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from datacloud_platform.platform_file_storage import (
    atomic_write_json,
    reap_orphan_tmp_files,
)


class TestAtomicWriteJson:
    def test_write_and_read(self, tmp_path: Path) -> None:
        """Normal cycle: write JSON, verify file exists with correct content."""
        path = tmp_path / "test.json"
        atomic_write_json(path, {"key": "value"})
        assert path.exists()

        data = json.loads(path.read_text(encoding="utf-8"))
        assert data == {"key": "value"}

    def test_write_overwrites_existing(self, tmp_path: Path) -> None:
        """Writing to an existing path atomically replaces it."""
        path = tmp_path / "config.json"
        path.write_text('{"old": true}', encoding="utf-8")

        atomic_write_json(path, {"new": "data"})

        data = json.loads(path.read_text(encoding="utf-8"))
        assert data == {"new": "data"}
        assert "old" not in data

    def test_writes_complex_data(self, tmp_path: Path) -> None:
        """Lists, nested dicts, unicode characters are preserved."""
        path = tmp_path / "complex.json"
        data = {
            "name": "测试",
            "items": [1, 2, 3],
            "nested": {"key": "值", "flag": True},
            "none_val": None,
        }
        atomic_write_json(path, data)
        result = json.loads(path.read_text(encoding="utf-8"))
        assert result == data

    def test_requires_parent_directory(self, tmp_path: Path) -> None:
        """atomic_write_json does NOT create parent dirs — caller must mkdir first."""
        path = tmp_path / "deep" / "nested" / "data.json"
        # Should fail because parent directories don't exist
        with pytest.raises(FileNotFoundError):
            atomic_write_json(path, {"ok": True})


class TestAtomicWriteCleanup:
    def test_cleanup_on_write_error(self, tmp_path: Path) -> None:
        """When json.dumps raises, the temp file is removed."""
        path = tmp_path / "bad.json"

        class Unserializable:
            pass

        with pytest.raises(TypeError):
            atomic_write_json(path, {"obj": Unserializable()})

        # After error, the destination path should NOT exist
        assert not path.exists()

        # And no .tmp.* file should be left behind
        tmp_glob = list(tmp_path.glob("bad.json.tmp.*"))
        assert len(tmp_glob) == 0, f"Orphan tmp files left: {tmp_glob}"

    def test_cleanup_on_replace_error(self, tmp_path: Path) -> None:
        """When os.replace fails (e.g. permission), temp file is removed."""
        path = tmp_path / "locked.json"
        path.write_text("original", encoding="utf-8")

        # Mock os.replace to raise OSError
        with patch("os.replace", side_effect=OSError("Simulated failure")):
            with pytest.raises(OSError, match="Simulated failure"):
                atomic_write_json(path, {"data": "should not be written"})

        # Destination unchanged
        assert path.read_text(encoding="utf-8") == "original"

        # No orphan tmp files
        tmp_glob = list(tmp_path.glob("locked.json.tmp.*"))
        assert len(tmp_glob) == 0, f"Orphan tmp files left: {tmp_glob}"


class TestReapOrphanTmpFiles:
    def test_reap_removes_tmp_files(self, tmp_path: Path) -> None:
        """Manually created .tmp.* files are cleaned up by reap."""
        orphan = tmp_path / "data.json.tmp.12345.67890"
        orphan.write_text("orphan", encoding="utf-8")

        reap_orphan_tmp_files(scan_dir=tmp_path)

        assert not orphan.exists(), f"Orphan file {orphan} was not reaped"

    def test_reap_skips_non_tmp_files(self, tmp_path: Path) -> None:
        """Regular files without .tmp.* suffix are left untouched."""
        real_file = tmp_path / "important.json"
        real_file.write_text('{"keep": true}', encoding="utf-8")

        reap_orphan_tmp_files(scan_dir=tmp_path)

        assert real_file.exists()
        assert json.loads(real_file.read_text(encoding="utf-8")) == {"keep": True}
