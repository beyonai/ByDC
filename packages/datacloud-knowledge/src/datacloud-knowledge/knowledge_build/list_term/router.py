"""列表术语构建路由。"""

from __future__ import annotations

from fastapi import APIRouter, UploadFile, File

from ..schema import TermCreateResponse, TermUpdateResponse, ImportResult
from . import service

router = APIRouter(prefix="/list-terms", tags=["知识构建-列表术语"])


@router.post("", response_model=TermCreateResponse)
async def create_list_term(
    term_name: str,
    term_type_code: str,
    domain_id: str,
    library_id: str | None = None,
    desc_summary: str | None = None,
) -> TermCreateResponse:
    """通过参数创建列表术语。"""
    result = await service.create_list_term(
        term_name=term_name,
        term_type_code=term_type_code,
        domain_id=domain_id,
        library_id=library_id,
        desc_summary=desc_summary,
    )
    return TermCreateResponse(**result)


@router.post("/import", response_model=ImportResult)
async def import_list_terms(
    file: UploadFile = File(...),
    domain_id: str = "",
    library_id: str | None = None,
) -> ImportResult:
    """通过文件批量导入列表术语（JSONL）。"""
    raise NotImplementedError


@router.put("/{term_id}", response_model=TermUpdateResponse)
async def update_list_term(term_id: str) -> TermUpdateResponse:
    """更新列表术语。"""
    result = await service.update_list_term(term_id)
    return TermUpdateResponse(**result)


@router.delete("/{term_id}", status_code=204)
async def delete_list_term(term_id: str) -> None:
    """删除列表术语。"""
    await service.delete_list_term(term_id)
