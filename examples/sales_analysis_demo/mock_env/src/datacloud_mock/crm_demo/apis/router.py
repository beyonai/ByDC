"""CRM 演示子系统 - API 路由."""

import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter()

# PO（人员组织）无 redis 等额外依赖，优先挂载
from datacloud_mock.crm_demo.apis.po.router import router as po_router

router.include_router(po_router)

# Todo、Expense 依赖 redis/notice，按需挂载
try:
    from datacloud_mock.crm_demo.apis.todo.router import router as todo_router
    router.include_router(todo_router)
except ImportError as e:
    logger.warning("todo router skipped (missing deps): %s", e)

try:
    from datacloud_mock.crm_demo.apis.expense.router import router as expense_router
    router.include_router(expense_router)
except ImportError as e:
    logger.warning("expense router skipped (missing deps): %s", e)


@router.get("/")
def crm_demo_root() -> dict:
    """CRM 演示子系统根路径."""
    return {"subsystem": "crm_demo", "message": "ok"}
