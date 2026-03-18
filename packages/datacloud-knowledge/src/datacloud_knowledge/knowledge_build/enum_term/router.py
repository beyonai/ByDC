"""枚举术语构建路由。"""

from __future__ import annotations

from fastapi import APIRouter, UploadFile, File

from ..schema import TermCreateResponse, TermUpdateResponse, ImportResult
from . import service

router = APIRouter(prefix="/enum-terms", tags=["知识构建-枚举术语"])


@router.post("", response_model=TermCreateResponse)
async def create_enum_term(
    term_name: str,
    term_type_code: str,
    domain_id: str,
    library_id: str | None = None,
    desc_summary: str | None = None,
) -> TermCreateResponse:
    """通过参数创建枚举/字典术语。"""
    result = await service.create_enum_term(
        term_name=term_name,
        term_type_code=term_type_code,
        domain_id=domain_id,
        library_id=library_id,
        desc_summary=desc_summary,
    )
    return TermCreateResponse(**result)


@router.post("/import", response_model=ImportResult)
async def import_enum_terms(
    file: UploadFile = File(...),
    domain_id: str = "",
    library_id: str | None = None,
) -> ImportResult:
    """通过文件批量导入枚举/字典术语（JSONL）。"""
    raise NotImplementedError


@router.put("/{term_id}", response_model=TermUpdateResponse)
async def update_enum_term(term_id: str) -> TermUpdateResponse:
    """更新枚举术语。"""
    result = await service.update_enum_term(term_id)
    return TermUpdateResponse(**result)


@router.delete("/{term_id}", status_code=204)
async def delete_enum_term(term_id: str) -> None:
    """删除枚举术语。"""
    await service.delete_enum_term(term_id)
