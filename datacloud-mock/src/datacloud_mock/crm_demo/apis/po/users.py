"""人员 API handlers."""

import sys
import traceback

from fastapi import APIRouter, Depends
from pydantic import AliasChoices, BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from datacloud_mock.crm_demo.db import get_session
from datacloud_mock.crm_demo.db.models import PoUsers, PoUsersOrganization

router = APIRouter()


# --- Request/Response schemas ---


class UsersQueryRequest(BaseModel):
    """按 ID 或名称查询人员."""

    userIds: list[str] | None = None
    names: list[str] | None = None


class UsersByOrgRequest(BaseModel):
    """按组织 ID 查询人员."""

    orgId: str
    includeSubOrgs: bool | None = Field(
        default=False,
        validation_alias=AliasChoices("includeSubOrgs", "includeSuborgs"),
    )


def _user_to_response(row: PoUsers, org_id: str | None) -> dict:
    """将 DB 行转为 API 响应格式."""
    return {
        "userId": str(row.user_id),
        "userName": row.user_name,
        "userNumber": row.user_number or "",
        "userCode": row.user_code or "",
        "orgId": org_id or "",
        "state": row.state,
    }


def _user_to_response_ext(row: PoUsers, org_id: str | None) -> dict:
    """按组织查询时返回更多字段."""
    base = _user_to_response(row, org_id)
    base["email"] = row.email or ""
    base["phone"] = row.phone or ""
    return base


@router.post("/users/query")
async def users_query_by_ids(
    body: UsersQueryRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """按用户 ID 或名称列表批量查询人员."""
    if not body.userIds and not body.names:
        return {"users": []}

    q = select(PoUsers)
    if body.userIds:
        try:
            # ids = [int(x) for x in body.userIds]
            q = q.where(PoUsers.user_code.in_(body.userIds))
        except ValueError:
            return {"users": []}
    elif body.names:
        q = q.where(
            (PoUsers.user_name.in_(body.names)) | (PoUsers.user_code.in_(body.names))
        )

    result = await session.execute(q)
    rows = result.scalars().all()

    # 获取每个用户的 org_id（取第一个关联组织）
    user_org_map: dict[int, str] = {}
    if rows:
        user_ids = [r.user_id for r in rows]
        org_q = select(PoUsersOrganization.user_id, PoUsersOrganization.org_id).where(
            PoUsersOrganization.user_id.in_(user_ids)
        )
        org_result = await session.execute(org_q)
        for uid, oid in org_result.all():
            if uid not in user_org_map:
                user_org_map[uid] = str(oid)

    users = [_user_to_response(r, user_org_map.get(r.user_id)) for r in rows]
    return {"users": users}


@router.post("/users/by-org")
async def users_query_by_org(
    body: UsersByOrgRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """按组织 ID 查询该组织下的人员列表."""
    try:
        return await _users_query_by_org_impl(body, session)
    except Exception:
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        raise


async def _users_query_by_org_impl(
    body: UsersByOrgRequest,
    session: AsyncSession,
) -> dict:
    """按组织 ID 查询人员（内部实现）."""
    try:
        org_id_int = int(body.orgId)
    except ValueError:
        return {"users": []}

    # 通过 po_users_organization 找到该组织下的 user_id
    subq = select(PoUsersOrganization.user_id).where(
        PoUsersOrganization.org_id == org_id_int
    )
    q = select(PoUsers).where(PoUsers.user_id.in_(subq))
    result = await session.execute(q)
    rows = result.scalars().all()

    org_id_str = str(org_id_int)
    users = [_user_to_response_ext(r, org_id_str) for r in rows]
    return {"users": users}
