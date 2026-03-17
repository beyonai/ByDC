"""PO (人员组织) 路由汇总."""

from fastapi import APIRouter

from datacloud_mock.crm_demo.apis.po import orgs, users

router = APIRouter(prefix="/po")

router.include_router(users.router, tags=["po-users"])
router.include_router(orgs.router, tags=["po-orgs"])
