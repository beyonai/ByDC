"""本体术语构建路由。"""

from __future__ import annotations

from fastapi import APIRouter, UploadFile, File

from ..schema import TermCreateResponse, TermUpdateResponse, ImportResult
from . import service

router = APIRouter(prefix="/ontology", tags=["知识构建-本体术语"])


@router.post("/terms", response_model=TermCreateResponse)
async def create_ontology_term(
    term_name: str,
    term_type_code: str,
    domain_id: str,
    library_id: str | None = None,
    owl_doc_id: str | None = None,
    desc_summary: str | None = None,
) -> TermCreateResponse:
    """通过参数创建本体术语。"""
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
