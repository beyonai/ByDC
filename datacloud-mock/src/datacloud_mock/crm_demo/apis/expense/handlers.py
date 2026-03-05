"""费用报备 API handlers - 4 个接口."""

from datetime import datetime

from fastapi import Body, Depends
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from datacloud_mock.crm_demo.db import get_session
from datacloud_mock.crm_demo.db.models import SalesExpenseReport

# --- Request schemas ---


class ExpenseApplyRequest(BaseModel):
    applicantEmpNo: str
    applicantName: str
    applicantOrgId: str
    expenseAmount: float
    expenseDesc: str | None = None
    relatedBoId: str | None = None
    relatedCustomerId: str | None = None


class ExpenseUpdateRequest(BaseModel):
    id: str
    expenseAmount: float | None = None
    expenseDesc: str | None = None
    relatedBoId: str | None = None
    relatedCustomerId: str | None = None
    applicantOrgId: str | None = None


class ExpenseApproveRequest(BaseModel):
    expenseReportIds: list[str]
    approvalStatus: str
    approvalComment: str | None = None


class ExpenseListRequest(BaseModel):
    applicantEmpNos: list[str] | None = None
    applicantOrgId: str | None = None
    approvalStatus: str | None = None
    applyTimeStart: str | None = None
    applyTimeEnd: str | None = None
    page: int | None = None
    pageSize: int | None = None


def _expense_to_item(row: SalesExpenseReport) -> dict:
    """将 DB 行转为列表项格式."""
    return {
        "id": str(row.id),
        "applicantEmpNo": row.applicant_emp_no,
        "applicantName": row.applicant_name,
        "applicantOrgId": row.applicant_org_id,
        "expenseAmount": float(row.expense_amount),
        "expenseDesc": row.expense_desc,
        "relatedBoId": row.related_bo_id,
        "relatedCustomerId": row.related_customer_id,
        "applyTime": row.apply_time.isoformat() if row.apply_time else None,
        "approvalStatus": row.approval_status,
        "approvalComment": row.approval_comment,
        "approvedAt": row.approved_at.isoformat() if row.approved_at else None,
    }


async def expense_apply(body: ExpenseApplyRequest, session: AsyncSession) -> dict:
    """申请费用报备."""
    now = datetime.utcnow()
    row = SalesExpenseReport(
        applicant_emp_no=body.applicantEmpNo,
        applicant_name=body.applicantName,
        applicant_org_id=body.applicantOrgId,
        expense_amount=body.expenseAmount,
        expense_desc=body.expenseDesc,
        related_bo_id=body.relatedBoId,
        related_customer_id=body.relatedCustomerId,
        apply_time=now,
        created_by=body.applicantEmpNo,
        created_time=now,
    )
    session.add(row)
    await session.flush()
    return {"id": str(row.id), "errorMsg": None, "status": "PENDING"}


async def expense_update(body: ExpenseUpdateRequest, session: AsyncSession) -> dict:
    """修改费用报备."""
    try:
        eid = int(body.id)
    except ValueError:
        return {"id": body.id, "status": "error", "updatedAt": None}
    vals = {}
    if body.expenseAmount is not None:
        vals["expense_amount"] = body.expenseAmount
    if body.expenseDesc is not None:
        vals["expense_desc"] = body.expenseDesc
    if body.relatedBoId is not None:
        vals["related_bo_id"] = body.relatedBoId
    if body.relatedCustomerId is not None:
        vals["related_customer_id"] = body.relatedCustomerId
    if body.applicantOrgId is not None:
        vals["applicant_org_id"] = body.applicantOrgId
    if vals:
        now = datetime.utcnow()
        vals["updated_time"] = now
        vals["updated_by"] = "system"
        await session.execute(
            update(SalesExpenseReport).where(SalesExpenseReport.id == eid).values(**vals)
        )
        return {"id": body.id, "status": "ok", "updatedAt": now.isoformat()}
    return {"id": body.id, "status": "ok", "updatedAt": None}


async def expense_approve(body: ExpenseApproveRequest, session: AsyncSession) -> dict:
    """批量审批费用报备."""
    status_map = {"Approving": "APPROVED", "Rejected": "REJECTED"}
    db_status = status_map.get(body.approvalStatus, "PENDING")
    now = datetime.utcnow()
    for eid_str in body.expenseReportIds:
        try:
            eid = int(eid_str)
        except ValueError:
            continue
        vals = {
            "approval_status": db_status,
            "approval_comment": body.approvalComment,
            "approved_at": now if db_status == "APPROVED" else None,
        }
        await session.execute(
            update(SalesExpenseReport).where(SalesExpenseReport.id == eid).values(**vals)
        )
    return {"id": body.expenseReportIds[0] if body.expenseReportIds else "", "approvalStatus": db_status}


async def expense_list(body: ExpenseListRequest, session: AsyncSession) -> dict:
    """查询费用报备列表."""
    q = select(SalesExpenseReport).where(SalesExpenseReport.is_deleted == False)
    if body.applicantEmpNos:
        q = q.where(SalesExpenseReport.applicant_emp_no.in_(body.applicantEmpNos))
    if body.applicantOrgId:
        q = q.where(SalesExpenseReport.applicant_org_id == body.applicantOrgId)
    if body.approvalStatus:
        q = q.where(SalesExpenseReport.approval_status == body.approvalStatus)
    if body.applyTimeStart:
        try:
            ts = datetime.fromisoformat(body.applyTimeStart.replace(" ", "T"))
            q = q.where(SalesExpenseReport.apply_time >= ts)
        except ValueError:
            pass
    if body.applyTimeEnd:
        try:
            ts = datetime.fromisoformat(body.applyTimeEnd.replace(" ", "T"))
            q = q.where(SalesExpenseReport.apply_time <= ts)
        except ValueError:
            pass
    q = q.order_by(SalesExpenseReport.id.desc())
    page = body.page or 1
    page_size = body.pageSize or 20
    q = q.offset((page - 1) * page_size).limit(page_size)
    result = await session.execute(q)
    rows = result.scalars().all()
    return {"expenseReports": [_expense_to_item(r) for r in rows]}
