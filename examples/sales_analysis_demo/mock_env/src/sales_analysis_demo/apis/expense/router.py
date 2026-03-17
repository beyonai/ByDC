"""费用报备路由汇总."""

from fastapi import APIRouter, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from sales_analysis_demo.apis.expense.handlers import (
    ExpenseApplyRequest,
    ExpenseApproveRequest,
    ExpenseListRequest,
    ExpenseUpdateRequest,
    expense_apply,
    expense_approve,
    expense_list,
    expense_update,
)
from sales_analysis_demo.db import get_session

router = APIRouter(prefix="/expense-reports")


@router.post("")
async def expense_apply_endpoint(
    body: ExpenseApplyRequest,
    session: AsyncSession = Depends(get_session),
):
    """申请费用报备."""
    return await expense_apply(body, session)


@router.post("/update")
async def expense_update_endpoint(
    body: ExpenseUpdateRequest,
    session: AsyncSession = Depends(get_session),
):
    """修改费用报备."""
    return await expense_update(body, session)


@router.post("/batch/approve")
async def expense_approve_endpoint(
    body: ExpenseApproveRequest,
    session: AsyncSession = Depends(get_session),
):
    """批量审批费用报备."""
    return await expense_approve(body, session)


@router.post("/list")
async def expense_list_endpoint(
    body: ExpenseListRequest = Body(default_factory=ExpenseListRequest),
    session: AsyncSession = Depends(get_session),
):
    """查询费用报备列表."""
    return await expense_list(body, session)
