"""Handler for the ``getFileByPage`` ext command."""

from __future__ import annotations

import csv
import itertools
import json
import re
from pathlib import Path
from typing import Any

from datacloud_analysis.workspace.runtime import resolve_shared_workspace_dir

_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def handle_get_file_by_page_command(
    *,
    ext_params: dict[str, Any],
    session_id: str,
    workspace_dir: str | None,
) -> tuple[bool, dict[str, Any] | None]:
    """Handle ext_params command and return (handled, 6001_payload)."""
    command = ext_params.get("command")
    if not isinstance(command, str) or not command.strip():
        return False, None

    command = command.strip()
    if command == "getFileByPage":
        return True, _build_6001_for_get_file_by_page(
            ext_params=ext_params,
            session_id=session_id,
            workspace_dir=workspace_dir,
        )
    return False, None


def handle_ext_command(
    *,
    ext_params: dict[str, Any],
    session_id: str,
    workspace_dir: str | None,
) -> tuple[bool, dict[str, Any] | None]:
    """Backward-compatible alias for legacy imports."""
    return handle_get_file_by_page_command(
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

    if not workspace_dir:
        return _make_6001_error("workspace_dir 不能为空", page=page, page_size=page_size)

    try:
        file_path, meta_path = _resolve_file_and_meta_paths(
            workspace_dir=workspace_dir,
            file_id=file_id,
        )
    except Exception as exc:  # noqa: BLE001
        return _make_6001_error(str(exc), page=page, page_size=page_size)

    try:
        meta_info = _read_meta_file(meta_path)
        if file_path.suffix.lower() == ".csv":
            records, total = _read_csv_page(file_path, page=page, page_size=page_size)
        else:
            file_meta, records, total, _ = _read_file_page(
                file_path=file_path,
                page=page,
                page_size=page_size,
            )
            if not meta_info:
                meta_info = file_meta
        return {
            "code": 0,
            "message": "success",
            "data": {
                "records": records,
                "meta": meta_info,
                "pagination": _pagination_dict(page, page_size, total),
                "file": {
                    "fileId": file_id,
                    "filePath": str(file_path),
                    "metaPath": str(meta_path) if meta_path.exists() else "",
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


def _resolve_file_and_meta_paths(*, workspace_dir: str, file_id: str) -> tuple[Path, Path]:
    workspace_root_raw = resolve_shared_workspace_dir(workspace_dir)
    if workspace_root_raw is None:
        raise FileNotFoundError("workspace_dir 不能为空")
    workspace_root = Path(str(workspace_root_raw))
    if not workspace_root.exists():
        raise FileNotFoundError(f"workspace_dir 不存在: {workspace_root}")

    if _UUID_PATTERN.fullmatch(file_id):
        csv_path = workspace_root / "exports" / f"{file_id}.csv"
        if csv_path.exists():
            return csv_path, workspace_root / "exports" / f"{file_id}_meta.json"

    rel_path = Path(file_id)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        raise ValueError("Invalid fileId (directory traversal not allowed)")

    direct_path = (workspace_root / rel_path).resolve()
    if _is_within(workspace_root, direct_path) and direct_path.exists() and direct_path.is_file():
        return direct_path, direct_path.with_name(f"{direct_path.stem}_meta.json")

    matches = [
        path.resolve()
        for path in workspace_root.rglob(rel_path.name)
        if path.is_file() and _is_within(workspace_root, path.resolve())
    ]
    if len(matches) == 1:
        match = matches[0]
        return match, match.with_name(f"{match.stem}_meta.json")
    if len(matches) > 1:
        raise ValueError(f"workspace_dir 下存在多个同名文件，请使用相对路径: {file_id}")
    raise FileNotFoundError(f"File not found in workspace_dir: {file_id}")


def _is_within(base: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(base)
        return True
    except ValueError:
        return False


def _shared_workspace_dir(workspace_dir: Path) -> Path:
    resolved = resolve_shared_workspace_dir(workspace_dir)
    if resolved is None:
        return workspace_dir.resolve()
    return Path(str(resolved))


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
        with open(file_path, encoding="utf-8") as fh:
            first_line = fh.readline()
            if not first_line:
                return meta_info, records, 0, _pagination_dict(page, page_size, 0)
            try:
                meta_info = json.loads(first_line)
            except json.JSONDecodeError:
                meta_info = {}
            for line in itertools.islice(fh, start_idx, end_idx):
                if line.strip():
                    records.append(json.loads(line))
        raw_total = meta_info.get("total")
        total = int(raw_total) if raw_total is not None else len(records)
        return meta_info, records, total, _pagination_dict(page, page_size, total)

    with open(file_path, encoding="utf-8") as fh:
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


def _read_meta_file(meta_path: Path) -> dict[str, Any]:
    """Read side-car metadata JSON, returning {} when missing."""
    if not meta_path.exists():
        return {}
    with open(meta_path, encoding="utf-8") as fh:
        content = json.load(fh)
    return content if isinstance(content, dict) else {}


def _read_csv_page(csv_path: Path, page: int, page_size: int) -> tuple[list[dict[str, Any]], int]:
    """Read one page from a CSV file and return records with total rows."""
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size

    all_rows: list[dict[str, Any]] = []
    with open(csv_path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            all_rows.append(dict(row))

    total = len(all_rows)
    records = all_rows[start_idx:end_idx]
    return records, total
