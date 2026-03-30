"""Handler for ``getFileByPage`` ext command."""

from __future__ import annotations

import itertools
import json
import os
from pathlib import Path
from typing import Any


def handle_get_file_by_page_command(
    *,
    ext_params: dict[str, Any],
    session_id: str,
    workspace_dir: str | None,
) -> tuple[bool, dict[str, Any] | None]:
    """Handle getFileByPage and return ``(handled, payload)``."""
    command = ext_params.get("command")
    if not isinstance(command, str) or command.strip() != "getFileByPage":
        return False, None

    return True, _build_6001_for_get_file_by_page(
        ext_params=ext_params,
        session_id=session_id,
        workspace_dir=workspace_dir,
    )


def _build_6001_for_get_file_by_page(
    *,
    ext_params: dict[str, Any],
    session_id: str,
    workspace_dir: str | None,
) -> dict[str, Any]:
    """Read file by page and build a 6001 envelope."""
    page = _to_int(ext_params.get("page"), default=1, minimum=1)
    page_size = _to_int(ext_params.get("pagesize"), default=50, minimum=1, maximum=500)
    file_id = str(ext_params.get("fileId") or "").strip()
    if not file_id:
        return _make_6001_error("fileId 不能为空", page=page, page_size=page_size)

    try:
        target_file = _resolve_workspace_file(
            session_id=session_id,
            file_id=file_id,
            workspace_dir=workspace_dir,
        )
        meta, records, _total, pagination = _read_file_page(
            file_path=target_file,
            page=page,
            page_size=page_size,
        )
        return {
            "code": 0,
            "message": "success",
            "data": {
                "records": records,
                "meta": meta,
                "pagination": pagination,
                "file": {
                    "fileId": file_id,
                    "path": str(target_file),
                },
            },
        }
    except Exception as exc:  # noqa: BLE001
        return _make_6001_error(str(exc), page=page, page_size=page_size)


def _to_int(
    raw: Any,
    *,
    default: int,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    """Parse int with clamped bounds and fallback."""
    try:
        value = int(str(raw).strip())
    except Exception:  # noqa: BLE001
        value = default
    if minimum is not None and value < minimum:
        value = minimum
    if maximum is not None and value > maximum:
        value = maximum
    return value


def _pagination_dict(page: int, page_size: int, total: int) -> dict[str, Any]:
    total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }


def _make_6001_error(message: str, page: int = 1, page_size: int = 50) -> dict[str, Any]:
    return {
        "code": 1,
        "message": message,
        "data": {
            "records": [],
            "meta": {},
            "pagination": _pagination_dict(page, page_size, 0),
            "file": {},
        },
    }


def _is_within(base: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(base)
    except ValueError:
        return False
    return True


def _resolve_workspace_file(session_id: str, file_id: str, workspace_dir: str | None) -> Path:
    rel_path = Path(file_id)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        raise ValueError("Invalid fileId (directory traversal not allowed)")

    root_dir = workspace_dir or os.getenv("DATACLOUD_GATEWAY_WORKSPACE_DIR") or "/tmp/datacloud"  # noqa: S108
    root = Path(root_dir).resolve()
    session_root = (root / session_id).resolve()

    candidate = (session_root / rel_path).resolve()
    if _is_within(session_root, candidate) and candidate.exists():
        return candidate

    fallback = (root / rel_path).resolve()
    if not _is_within(root, fallback):
        raise ValueError("Invalid fileId (outside workspace)")
    if not fallback.exists():
        raise FileNotFoundError(f"File not found: {file_id}")
    return fallback


def _read_file_page(
    *,
    file_path: Path,
    page: int,
    page_size: int,
) -> tuple[dict[str, Any], list[Any], int, dict[str, Any]]:
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size

    if file_path.suffix == ".jsonl":
        meta_info: dict[str, Any] = {}
        records: list[Any] = []
        with file_path.open("r", encoding="utf-8") as fh:
            first_line = fh.readline()
            if not first_line:
                return meta_info, records, 0, _pagination_dict(page, page_size, 0)
            try:
                meta_info = json.loads(first_line)
            except json.JSONDecodeError:
                meta_info = {}
            records.extend(
                json.loads(line) for line in itertools.islice(fh, start_idx, end_idx) if line.strip()
            )
        raw_total = meta_info.get("total")
        if raw_total is None:
            raise ValueError("JSONL file first line meta missing total field, cannot paginate")
        total = int(raw_total)
        return meta_info, records, total, _pagination_dict(page, page_size, total)

    with file_path.open("r", encoding="utf-8") as fh:
        content = json.load(fh)
    if isinstance(content, list):
        total = len(content)
        records = content[start_idx:end_idx]
        return {}, records, total, _pagination_dict(page, page_size, total)
    if isinstance(content, dict) and "records" in content:
        all_records = content.get("records") or []
        total = int(content.get("total", len(all_records)))
        records = all_records[start_idx:end_idx]
        meta = content.get("meta", {}) if isinstance(content.get("meta"), dict) else {}
        return meta, records, total, _pagination_dict(page, page_size, total)
    raise ValueError("Only json/jsonl files with records are supported")
