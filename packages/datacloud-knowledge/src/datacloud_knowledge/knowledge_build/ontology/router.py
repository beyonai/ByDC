"""本体术语构建路由。"""

from __future__ import annotations

import asyncio
import io
import logging

from fastapi import APIRouter, Depends, File, Form, UploadFile

from ...file_store import FileManager

from ..deps import get_file_manager
from ..schema import ImportResult, TermCreateResponse, TermUpdateResponse
from . import service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ontology", tags=["知识构建-本体术语"])


@router.post("/terms", response_model=TermCreateResponse)
async def create_ontology_term(
    term_name: str = Form(...),
    term_type_code: str = Form(...),
    domain_id: str = Form(...),
    library_id: str | None = Form(default=None),
    owl_doc_id: str | None = Form(default=None),
    desc_summary: str | None = Form(default=None),
    owl_file: UploadFile | None = File(default=None),
    file_manager: FileManager = Depends(get_file_manager),
) -> TermCreateResponse:
    """通过参数创建本体术语。

    若同时提供 owl_file，将先通过 FileManager 上传文件，以返回的 md5 作为
    owl_doc_id 写入术语记录（文件上传结果优先，覆盖同名表单字段）。
    """
    if owl_file is not None:
        content = await owl_file.read()
        upload_results = await asyncio.to_thread(
            file_manager.upload_many,
            [
                {
                    "stream": io.BytesIO(content),
                    "filename": owl_file.filename or "ontology.owl",
                    "content_type": owl_file.content_type or "",
                    "directory": "ontology",
                }
            ],
        )
        owl_doc_id = upload_results[0].md5
        logger.info(
            "owl file uploaded: filename=%s md5=%s",
            owl_file.filename,
            owl_doc_id,
        )

    result = await service.create_ontology_term(
        term_name=term_name,
        term_type_code=term_type_code,
        domain_id=domain_id,
        library_id=library_id,
        owl_doc_id=owl_doc_id,
        desc_summary=desc_summary,
    )
    return TermCreateResponse(**result)


@router.post("/terms/import", response_model=ImportResult)
async def import_ontology_terms(
    file: UploadFile = File(...),
    domain_id: str = "",
    library_id: str | None = None,
) -> ImportResult:
    """通过文件批量导入本体术语（JSON / JSONL）。"""
    raise NotImplementedError


@router.put("/terms/{term_id}", response_model=TermUpdateResponse)
async def update_ontology_term(term_id: str) -> TermUpdateResponse:
    """更新本体术语。"""
    result = await service.update_ontology_term(term_id)
    return TermUpdateResponse(**result)


@router.delete("/terms/{term_id}", status_code=204)
async def delete_ontology_term(term_id: str) -> None:
    """删除本体术语。"""
    await service.delete_ontology_term(term_id)
