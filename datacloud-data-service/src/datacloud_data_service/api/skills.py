"""Skills API: GET /package 返回技能包 JSON。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from datacloud_data_service.tools.skill_package_generator import SkillPackageGenerator

router = APIRouter()


@router.get("/package")
async def get_skill_package(
    request: Request,
    view_id: str | None = None,
    object_ids: str | None = None,
) -> dict:
    """获取技能包。

    查询参数:
        view_id: 场景 ID
        object_ids: 对象 ID 列表，逗号分隔

    至少需传 view_id 或 object_ids 其一。
    """
    tenant_id = request.headers.get("X-Tenant-Id", "")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-Id required")

    has_view_id = view_id is not None and view_id.strip() != ""
    object_ids_list: list[str] = []
    if object_ids:
        object_ids_list = [s.strip() for s in object_ids.split(",") if s.strip()]
    has_object_ids = len(object_ids_list) > 0

    if not has_view_id and not has_object_ids:
        raise HTTPException(
            status_code=400,
            detail="view_id or object_ids required (at least one)",
        )

    loader = getattr(request.app.state, "loader", None)
    if loader is None:
        raise HTTPException(
            status_code=500,
            detail="OntologyLoader not initialized",
        )

    generator = SkillPackageGenerator(loader)
    result = generator.generate(
        view_id=view_id.strip() if has_view_id else None,
        object_ids=object_ids_list if has_object_ids else None,
    )
    return result
