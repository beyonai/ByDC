"""知识构建路由聚合：知识包导入接口。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from .importer import precheck, runner
from .schema import ImportPackageRequest, ImportPackageRunRequest, PrecheckResult, RunResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/build", tags=["知识构建"])


@router.post(
    "/import-package/precheck",
    response_model=PrecheckResult,
    summary="知识包预检(纯校验)",
    description=(
        "对指定文件夹的知识包进行全量校验，不写库、不触发回调。"
        "适合调试阶段检查文件格式和引用完整性。"
    ),
)
def precheck_import_package(req: ImportPackageRequest) -> PrecheckResult:
    """预检知识包，全内存校验，不写数据库。"""
    try:
        result = precheck.run(req.folder_path)
    except Exception as exc:
        logger.exception("precheck error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return PrecheckResult(**result)


@router.post(
    "/import-package/run",
    response_model=RunResult,
    summary="知识包导入(预检+入库+回调)",
    description=(
        "完整导入流程:\n"
        "1. 预检:全量校验文件格式与引用完整性\n"
        "2. 预检通过->单事务入库，失败整体回滚\n"
        "3. 不论成功/失败，若配置了callback则通知源系统\n\n"
        "callback.method支持GET/POST(默认POST)。\n"
        "callback网络故障只记录日志，不影响本接口返回。"
    ),
)
def run_import_package(req: ImportPackageRunRequest) -> RunResult:
    """预检 + 入库 + 回调全流程。"""
    cb = req.callback
    try:
        result = runner.run(
            folder_path=req.folder_path,
            callback_url=cb.url if cb else None,
            callback_method=cb.method if cb else "POST",
            callback_headers=cb.headers if cb else {},
        )
    except Exception as exc:
        logger.exception("run error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return RunResult(**result)
