"""CRM 演示子系统 - API 路由."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def crm_demo_root() -> dict:
    """CRM 演示子系统根路径."""
    return {"subsystem": "crm_demo", "message": "ok"}
