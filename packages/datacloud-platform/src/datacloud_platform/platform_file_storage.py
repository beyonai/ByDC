"""Factories for persistent result-file storage backends."""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

from datacloud_data_sdk.file_storage import LocalResultFileStorage
from datacloud_data_sdk.file_storage.base import ResultFileStorage

from datacloud_platform.config import Settings

logger = logging.getLogger(__name__)


def build_result_file_storage(settings: Settings) -> ResultFileStorage:
    """Build the local result-file storage backend."""
    return LocalResultFileStorage(
        settings.result_file_base_dir or settings.csv_base_dir
    )


def _data_dir() -> Path:
    """Return the datacloud data directory from env or default."""
    env = os.environ.get("DATACLOUD_DATA_DIR")
    if env:
        return Path(env)
    return Path.home() / ".datacloud"


def atomic_write_json(path: Path, data: Any) -> None:
    """Atomically write JSON data to *path* via a temp-file + rename.

    The temporary file is named ``{path}.tmp.{pid}.{thread_id}`` so that
    concurrent writers targeting the same destination file do not collide.
    On any exception the temp file is removed before the error propagates.
    """
    pid = os.getpid()
    tid = threading.get_ident()
    tmp_path = path.with_suffix(f"{path.suffix}.tmp.{pid}.{tid}")

    try:
        tmp_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(tmp_path, path)
    except Exception:
        _cleanup_tmp(tmp_path)
        raise


def reap_orphan_tmp_files(*, scan_dir: Path | None = None) -> None:
    """Remove orphan ``.tmp.*`` files left behind by crashed writers.

    By default scans the datacloud data directory.  Pass *scan_dir* to
    restrict the scan to a specific directory (e.g. in tests).

    Args:
        scan_dir: Directory to scan. Defaults to ``DATACLOUD_DATA_DIR``
            or ``~/.datacloud``.
    """
    if scan_dir is None:
        scan_dir = _data_dir()

    orphan_count = 0
    if not scan_dir.exists():
        return
    try:
        for tmp_file in scan_dir.rglob("*.tmp.*"):
            try:
                tmp_file.unlink(missing_ok=True)
                orphan_count += 1
            except OSError:
                pass
    except Exception:
        logger.exception("reap_orphan_tmp_files: unexpected error during scan")
    else:
        if orphan_count:
            logger.info("Reaped %d orphan tmp file(s)", orphan_count)


def _cleanup_tmp(tmp_path: Path) -> None:
    """Best-effort removal of a temp file, logging failures."""
    try:
        tmp_path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Failed to clean up temp file %s", tmp_path, exc_info=True)
