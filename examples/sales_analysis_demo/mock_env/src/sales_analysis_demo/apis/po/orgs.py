"""组织 API handlers."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sales_analysis_demo.db import get_session
from sales_analysis_demo.db.models import PoOrganization

router = APIRouter()


# --- Request schemas ---


class OrgsQueryRequest(BaseModel):
    """按 ID 或名称查询组织."""

    orgIds: list[str] | None = None
    orgNames: list[str] | None = None


class OrgsChildrenRequest(BaseModel):
    """查询下级组织."""

    orgId: str
    recursive: bool | None = False


@router.post("/organizations/query")
async def orgs_query_by_ids(
    body: OrgsQueryRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """按组织 ID 或名称列表批量查询组织."""
    if not body.orgIds and not body.orgNames:
        return {"organizations": []}

    q = select(PoOrganization)
    if body.orgIds:
        try:
            ids = [int(x) for x in body.orgIds]
            q = q.where(PoOrganization.org_id.in_(ids))
        except ValueError:
            return {"organizations": []}
    elif body.orgNames:
        q = q.where(PoOrganization.org_name.in_(body.orgNames))

    result = await session.execute(q)
    rows = result.scalars().all()
    orgs = [
        {
            "org_id": str(r.org_id),
            "org_name": r.org_name,
            "org_code": r.org_code,
            "parent_org_id": str(r.parent_org_id),
        }
        for r in rows
    ]
    return {"organizations": orgs}


@router.post("/organizations/children")
async def orgs_query_children(
    body: OrgsChildrenRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """按组织 ID 查询其下级组织列表."""
    try:
        parent_id = int(body.orgId)
    except ValueError:
        return {"organizations": []}

    q = select(PoOrganization).where(PoOrganization.parent_org_id == parent_id)
    result = await session.execute(q)
    rows = result.scalars().all()

    if body.recursive:
        # 递归查询：收集所有下级
        all_orgs: list[dict] = []
        to_process = list(rows)
        seen_ids = {r.org_id for r in rows}
        while to_process:
            for r in to_process:
                all_orgs.append(
                    {
                        "orgId": str(r.org_id),
                        "orgName": r.org_name,
                        "orgCode": r.org_code,
                        "parentOrgId": str(r.parent_org_id),
                        "orgLevel": r.org_level,
                        "orgType": r.org_type or "",
                    }
                )
                seen_ids.add(r.org_id)
            next_parent_ids = [r.org_id for r in to_process]
            next_q = select(PoOrganization).where(
                PoOrganization.parent_org_id.in_(next_parent_ids),
                ~PoOrganization.org_id.in_(seen_ids),
            )
            next_result = await session.execute(next_q)
            to_process = list(next_result.scalars().all())
            for r in to_process:
                seen_ids.add(r.org_id)
        return {"organizations": all_orgs}

    orgs = [
        {
            "orgId": str(r.org_id),
            "orgName": r.org_name,
            "orgCode": r.org_code,
            "parentOrgId": str(r.parent_org_id),
            "orgLevel": r.org_level,
            "orgType": r.org_type or "",
        }
        for r in rows
    ]
    return {"organizations": orgs}
