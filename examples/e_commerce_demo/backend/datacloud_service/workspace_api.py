"""Standalone FastAPI application to serve workspace files via pagination."""

from __future__ import annotations

import csv
import itertools
import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

app = FastAPI(title="DataCloud Workspace API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_workspace_root() -> Path:
    # Match the environment variable from data.py
    root = os.getenv("DATACLOUD_GATEWAY_WORKSPACE_DIR", "/tmp/datacloud")
    return Path(root)


def _is_within(base: Path, candidate: Path) -> bool:
    """Return True when candidate is inside base."""
    try:
        candidate.relative_to(base)
        return True
    except ValueError:
        return False


def _slice_for_page(page: int, page_size: int) -> tuple[int, int]:
    """Convert 1-based page + page_size to [start, end) indices over data rows."""
    start = (page - 1) * page_size
    end = start + page_size
    return start, end


def _pagination_dict(
    page: int,
    page_size: int,
    total: int,
) -> dict[str, Any]:
    total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }


class WorkspaceFileRequest(BaseModel):
    session_id: str = Field(..., description="The session or task ID")
    relative_path: str = Field(..., description="The relative file path under the session directory")
    page: int = Field(1, ge=1, description="Page number (1-based)")
    page_size: int = Field(50, ge=1, le=500, description="Rows per page")
    download: bool = Field(False, description="If True, returns the file for direct download")


@app.post("/api/v1/workspace/files")
async def read_workspace_file(request: WorkspaceFileRequest = Body(...)):
    session_id = request.session_id
    relative_path = request.relative_path
    page = request.page
    page_size = request.page_size
    download = request.download
    rel_path_obj = Path(relative_path)
    # if rel_path_obj.is_absolute() or ".." in rel_path_obj.parts:
    #     raise HTTPException(status_code=400, detail="Invalid relative path (directory traversal not allowed).")

    root = get_workspace_root()
    target_dir = (root / session_id).resolve()
    target_file = (target_dir / rel_path_obj).resolve()

    # if not _is_within(target_dir, target_file):
    #     raise HTTPException(status_code=400, detail="Invalid relative path (outside session directory).")

    if not target_file.exists():
        # Fallback trying just root/relative_path if path is resolved differently
        fallback_file = (root / rel_path_obj).resolve()
        if not _is_within(root.resolve(), fallback_file):
            raise HTTPException(status_code=400, detail="Invalid relative path (outside workspace).")
        target_file = fallback_file
        if not target_file.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {relative_path}")
            
    if download:
        filename = target_file.name
        return FileResponse(path=target_file, filename=filename)

    start_idx, end_idx = _slice_for_page(page, page_size)

    # Read as JSONL pagination
    if target_file.suffix == ".jsonl":
        meta_info: dict[str, Any] = {}
        records: list[Any] = []
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                first_line = f.readline()
                if not first_line:
                    return JSONResponse(
                        {
                            "meta": {},
                            "records": [],
                            "total": 0,
                            "pagination": _pagination_dict(page, page_size, 0),
                        }
                    )

                try:
                    meta_info = json.loads(first_line)
                except json.JSONDecodeError:
                    meta_info = {}

                for line in itertools.islice(f, start_idx, end_idx):
                    if line.strip():
                        records.append(json.loads(line))

            raw_total = meta_info.get("total")
            if raw_total is not None:
                full_total = int(raw_total)
            else:
                full_total = len(records)

            return JSONResponse(
                {
                    "meta": meta_info,
                    "records": records,
                    "total": full_total,
                    "pagination": _pagination_dict(page, page_size, full_total),
                }
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
    elif target_file.suffix == ".csv":
        try:
            meta_info: dict[str, Any] = {}
            meta_file = target_file.parent / (target_file.stem + "_meta.json")
            if meta_file.exists():
                try:
                    with open(meta_file, "r", encoding="utf-8") as mf:
                        meta_info = json.load(mf)
                except Exception:
                    meta_info = {}

            with open(target_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                total = len(rows)
                return JSONResponse(
                    {
                        "meta": meta_info,
                        "records": rows[start_idx:end_idx],
                        "total": total,
                        "pagination": _pagination_dict(page, page_size, total),
                    }
                )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
    else:
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                content = json.load(f)
                if isinstance(content, list):
                    total = len(content)
                    return JSONResponse(
                        {
                            "meta": {},
                            "records": content[start_idx:end_idx],
                            "total": total,
                            "pagination": _pagination_dict(page, page_size, total),
                        }
                    )
                if isinstance(content, dict) and "records" in content:
                    records = content["records"]
                    total = int(content.get("total", len(records)))
                    return JSONResponse(
                        {
                            "meta": content.get("meta", {}),
                            "records": records[start_idx:end_idx],
                            "total": total,
                            "pagination": _pagination_dict(page, page_size, total),
                        }
                    )
                return JSONResponse(content)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail="Cannot parse non-JSONL as stream directly: " + str(e),
            ) from e

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting DataCloud Workspace File API on port 8081...")
    uvicorn.run(app, host="0.0.0.0", port=8081)
