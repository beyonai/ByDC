"""CRM 演示子系统 - API 路由."""

from fastapi import APIRouter

from datacloud_mock.crm_demo.apis.expense.router import router as expense_router
from datacloud_mock.crm_demo.apis.po.router import router as po_router
from datacloud_mock.crm_demo.apis.todo.router import router as todo_router

router = APIRouter()

router.include_router(po_router)
router.include_router(todo_router)
router.include_router(expense_router)


@router.get("/")
def crm_demo_root() -> dict:
    """CRM 演示子系统根路径."""
    return {"subsystem": "crm_demo", "message": "ok"}
