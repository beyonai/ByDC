"""Standalone FastAPI application to serve workspace files via pagination."""

import os
import json
import itertools
from typing import Any, Dict, List, Optional
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

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

@app.get("/api/v1/workspace/files")
async def read_workspace_file(
    session_id: str = Query(..., description="The session or task ID"),
    relative_path: str = Query(..., description="The relative file path under the session directory"),
    start_line: int = Query(0, description="Pagination start index (0-based)"),
    end_line: int = Query(50, description="Pagination end index (exclusive)"),
    download: bool = Query(False, description="If True, returns the file for direct download")
):
    if ".." in relative_path or relative_path.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid relative path (directory traversal not allowed).")
        
    root = get_workspace_root()
    target_dir = root / session_id
    target_file = target_dir / relative_path
    
    # In some hook logic the workspace path might already have session_id incorporated or be flatter
    if target_file.is_absolute():
        raise HTTPException(status_code=400, detail="Path must be relative.")
    
    if not target_file.exists():
        # Fallback trying just root/relative_path if path is resolved differently
        target_file = root / relative_path
        if not target_file.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {relative_path}")
            
    if download:
        filename = target_file.name
        return FileResponse(path=target_file, filename=filename)
        
    # Read as JSONL pagination
    if target_file.suffix == '.jsonl':
        meta_info = {}
        records = []
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                # Read the first line as META
                first_line = f.readline()
                if not first_line:
                    return JSONResponse({"meta": {}, "records": [], "total": 0})
                
                try:
                    meta_info = json.loads(first_line)
                except json.JSONDecodeError:
                    meta_info = {}
                
                # Fetch only start_line to end_line using islice
                # Note: line 2 in the file is conceptually records index 0
                for line in itertools.islice(f, start_line, end_line):
                    if line.strip():
                        records.append(json.loads(line))
                        
            return JSONResponse({
                "meta": meta_info,
                "records": records,
                "total": meta_info.get("total", len(records))
            })
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    else:
        # Fallback for standard JSON or CSV
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                content = json.load(f)
                if isinstance(content, list):
                    return JSONResponse({
                        "meta": {},
                        "records": content[start_line:end_line],
                        "total": len(content)
                    })
                elif isinstance(content, dict) and "records" in content:
                    records = content["records"]
                    return JSONResponse({
                        "meta": content.get("meta", {}),
                        "records": records[start_line:end_line],
                        "total": content.get("total", len(records))
                    })
                return JSONResponse(content)
        except Exception as e:
            raise HTTPException(status_code=500, detail="Cannot parse non-JSONL as stream directly: " + str(e))

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting DataCloud Workspace File API on port 8081...")
    uvicorn.run(app, host="0.0.0.0", port=8081)
