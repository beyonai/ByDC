"""Workspace API — 工作区模式本体管理 REST 接口（factory pattern）。

将 OntologyWorkspaceMixin + WorkspaceActionMixin 的核心能力暴露为 HTTP API。

端点：
    POST /api/v1/ontology-manager/workspace/init
    GET  /api/v1/ontology-manager/workspace/list
    GET  /api/v1/ontology-manager/workspace/{workspace_name}
    POST /api/v1/ontology-manager/workspace/delete
    POST /api/v1/ontology-manager/workspace/batch-submit

    POST /api/v1/ontology-manager/object/collect
    POST /api/v1/ontology-manager/object/delete
    GET  /api/v1/ontology-manager/object/list
    GET  /api/v1/ontology-manager/object/{entity_code}
    GET  /api/v1/ontology-manager/object/{entity_code}/fields

    POST /api/v1/ontology-manager/view/collect
    POST /api/v1/ontology-manager/view/delete
    GET  /api/v1/ontology-manager/view/list
    GET  /api/v1/ontology-manager/view/{view_code}

    POST /api/v1/ontology-manager/object/collect-action
    POST /api/v1/ontology-manager/object/delete-action
    GET  /api/v1/ontology-manager/object/{entity_code}/actions
    GET  /api/v1/ontology-manager/object/{entity_code}/action/{action_code}

    GET  /api/v1/ontology-manager/workspace/{workspace_name}/sdk/{entity_code}
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from datacloud_platform.platform import DatacloudPlatform

logger = logging.getLogger(__name__)


# ── FastAPI Dependency ──────────────────────────────────────────────────────


def _extract_user_code(request: Request) -> str:
    """从 HTTP header 提取用户标识。"""
    return request.headers.get("X-User-Code", "")


# ── Pydantic 请求模型 ───────────────────────────────────────────────────────


class WorkspaceInitRequest(BaseModel):
    workspace_name: str = Field(..., min_length=1, alias="workspace_name")
    workspace_desc: str = Field(default="", alias="workspace_desc")
    object_codes: list[str] | None = Field(default=None, alias="object_codes")


class WorkspaceDeleteRequest(BaseModel):
    workspace_name: str = Field(..., min_length=1, alias="workspace_name")


class BatchSubmitRequest(BaseModel):
    workspace_name: str = Field(..., min_length=1, alias="workspace_name")
    base_id: str = Field(default="", alias="base_id")
    only: list[str] = Field(default_factory=list, alias="only")
    confirm_drop_columns: bool = Field(default=False, alias="confirm_drop_columns")


class WorkspaceObjectCollectRequest(BaseModel):
    workspace_name: str = Field(default="", alias="workspace_name")
    entity_code: str = Field(..., min_length=1, alias="entity_code")
    entity_name: str = Field(default="", alias="entity_name")
    entity_desc: str = Field(default="", alias="entity_desc")
    table_name: str | None = Field(default=None, alias="table_name")
    fields: list[dict[str, Any]] | None = Field(default=None, alias="fields")
    term_sync: dict[str, Any] | None = Field(default=None, alias="term_sync")


class WorkspaceObjectDeleteRequest(BaseModel):
    workspace_name: str = Field(default="", alias="workspace_name")
    entity_code: str = Field(..., min_length=1, alias="entity_code")


class WorkspaceViewCollectRequest(BaseModel):
    workspace_name: str = Field(default="", alias="workspace_name")
    view_code: str = Field(..., min_length=1, alias="view_code")
    view_name: str = Field(default="", alias="view_name")
    view_desc: str = Field(default="", alias="view_desc")
    object_codes: list[str] | None = Field(default=None, alias="object_codes")
    object_relations: list[dict[str, Any]] | None = Field(
        default=None, alias="object_relations"
    )
    fields: list[dict[str, Any]] | None = Field(default=None, alias="fields")


class WorkspaceViewDeleteRequest(BaseModel):
    workspace_name: str = Field(default="", alias="workspace_name")
    view_code: str = Field(..., min_length=1, alias="view_code")


class CollectActionRequest(BaseModel):
    workspace_name: str = Field(..., min_length=1, alias="workspace_name")
    entity_code: str = Field(..., min_length=1, alias="entity_code")
    action_code: str = Field(..., min_length=1, alias="action_code")
    action_name: str = Field(..., min_length=1, alias="action_name")
    script: str = Field(..., min_length=1, alias="script")
    params: list[dict[str, Any]] = Field(default_factory=list, alias="params")
    action_desc: str = Field(default="", alias="action_desc")
    action_type: str = Field(default="OPERATION", alias="action_type")
    permission_roles: list[str] | None = Field(default=None, alias="permission_roles")
    object_references: list[str] | None = Field(default=None, alias="object_references")


class DeleteActionRequest(BaseModel):
    workspace_name: str = Field(..., min_length=1, alias="workspace_name")
    entity_code: str = Field(..., min_length=1, alias="entity_code")
    action_code: str = Field(..., min_length=1, alias="action_code")


class RunActionRequest(BaseModel):
    workspace_name: str = Field(..., min_length=1, alias="workspace_name")
    entity_code: str = Field(..., min_length=1, alias="entity_code")
    action_code: str = Field(..., min_length=1, alias="action_code")
    params: dict[str, Any] = Field(default_factory=dict, alias="params")
    script: str | None = Field(default=None, alias="script")


# ── Factory ─────────────────────────────────────────────────────────────────


def create_workspace_routes(platform: DatacloudPlatform) -> APIRouter:
    """创建工作区管理路由。

    Args:
        platform: 已配置的 DatacloudPlatform 实例。

    Returns:
        APIRouter with prefix ``/api/v1/ontology-manager``。
    """
    router = APIRouter(prefix="/api/v1/ontology-manager/workspace", tags=["Workspace"])

    # ═══════════════════════════════════════════════════════════════════════
    # 工作区管理
    # ═══════════════════════════════════════════════════════════════════════

    @router.post("/init")
    async def workspace_init(
        body: WorkspaceInitRequest,
        _user_code: str = Depends(_extract_user_code),
    ) -> Any:
        """初始化工作区。"""
        try:
            return platform.workspace_init(
                user_code=_user_code,
                workspace_name=body.workspace_name,
                workspace_desc=body.workspace_desc,
                object_codes=body.object_codes or None,
            )
        except Exception as exc:
            logger.exception("workspace/init 失败")
            return {"ok": False, "error": str(exc)}

    @router.get("/list")
    async def workspace_list(
        _user_code: str = Depends(_extract_user_code),
    ) -> Any:
        """列出用户所有工作区。"""
        try:
            return platform.workspace_list(user_code=_user_code)
        except Exception as exc:
            logger.exception("workspace/list 失败")
            return {"ok": False, "error": str(exc)}

    @router.get("/{workspace_name}")
    async def workspace_get(
        workspace_name: str,
        _user_code: str = Depends(_extract_user_code),
    ) -> Any:
        """查询工作区状态。"""
        try:
            return platform.workspace_get(
                user_code=_user_code, workspace_name=workspace_name
            )
        except Exception as exc:
            logger.exception("workspace/get 失败")
            return {"ok": False, "error": str(exc)}

    @router.post("/delete")
    async def workspace_delete(
        body: WorkspaceDeleteRequest,
        _user_code: str = Depends(_extract_user_code),
    ) -> Any:
        """删除工作区（不可逆）。"""
        try:
            return platform.workspace_delete(
                user_code=_user_code, workspace_name=body.workspace_name
            )
        except Exception as exc:
            logger.exception("workspace/delete 失败")
            return {"ok": False, "error": str(exc)}

    @router.post("/batch-submit")
    async def workspace_batch_submit(
        body: BatchSubmitRequest,
        _user_code: str = Depends(_extract_user_code),
    ) -> Any:
        """批量提交工作区中所有对象和视图。"""
        try:
            return platform.workspace_batch_submit(
                user_code=_user_code,
                workspace_name=body.workspace_name,
                base_id=body.base_id,
                only=body.only or None,
                confirm_drop_columns=body.confirm_drop_columns,
            )
        except Exception as exc:
            logger.exception("workspace/batch-submit 失败")
            return {"ok": False, "error": str(exc)}

    # ═══════════════════════════════════════════════════════════════════════
    # 对象管理（工作区模式）
    # ═══════════════════════════════════════════════════════════════════════

    @router.post("/object/collect")
    async def object_collect(
        body: WorkspaceObjectCollectRequest,
        _user_code: str = Depends(_extract_user_code),
    ) -> Any:
        """收集对象字段定义（工作区模式，多轮合并）。"""
        try:
            # 工作区模式：有 workspace_name 时走新路径
            if body.workspace_name:
                return platform.collect_object_to_workspace(
                    user_code=_user_code,
                    workspace_name=body.workspace_name,
                    entity_code=body.entity_code,
                    entity_name=body.entity_name,
                    entity_desc=body.entity_desc,
                    fields=body.fields,
                    term_sync=body.term_sync,
                    table_name=body.table_name,
                )
            # 无 workspace_name：退回旧 session 模式
            return platform.collect_object_info(
                user_code=_user_code,
                entity_code=body.entity_code,
                entity_name=body.entity_name,
                entity_desc=body.entity_desc,
                fields=body.fields,
            )
        except Exception as exc:
            logger.exception("object/collect 失败")
            return {"ok": False, "error": str(exc)}

    @router.post("/object/delete")
    async def object_delete(
        body: WorkspaceObjectDeleteRequest,
        _user_code: str = Depends(_extract_user_code),
    ) -> Any:
        """删除工作区对象。"""
        try:
            if body.workspace_name:
                return platform.delete_workspace_object(
                    user_code=_user_code,
                    workspace_name=body.workspace_name,
                    entity_code=body.entity_code,
                )
            return platform.delete_build_object(
                user_code=_user_code,
                entity_code=body.entity_code,
            )
        except Exception as exc:
            logger.exception("object/delete 失败")
            return {"ok": False, "error": str(exc)}

    @router.get("/object/list")
    async def object_list(
        workspace_name: str,
        _user_code: str = Depends(_extract_user_code),
    ) -> Any:
        """列出工作区所有对象。"""
        try:
            return platform.list_workspace_objects(
                user_code=_user_code, workspace_name=workspace_name
            )
        except Exception as exc:
            logger.exception("object/list 失败")
            return {"ok": False, "error": str(exc)}

    @router.get("/object/{entity_code}")
    async def object_get(
        entity_code: str,
        workspace_name: str,
        _user_code: str = Depends(_extract_user_code),
    ) -> Any:
        """获取对象完整定义。"""
        try:
            return platform.get_workspace_object(
                user_code=_user_code,
                workspace_name=workspace_name,
                entity_code=entity_code,
            )
        except Exception as exc:
            logger.exception("object/get 失败")
            return {"ok": False, "error": str(exc)}

    @router.get("/object/{entity_code}/fields")
    async def object_fields(
        entity_code: str,
        workspace_name: str,
        _user_code: str = Depends(_extract_user_code),
    ) -> Any:
        """获取对象字段列表。"""
        try:
            return platform.get_workspace_object_fields(
                user_code=_user_code,
                workspace_name=workspace_name,
                entity_code=entity_code,
            )
        except Exception as exc:
            logger.exception("object/fields 失败")
            return {"ok": False, "error": str(exc)}

    # ═══════════════════════════════════════════════════════════════════════
    # 视图管理（工作区模式）
    # ═══════════════════════════════════════════════════════════════════════

    @router.post("/view/collect")
    async def view_collect(
        body: WorkspaceViewCollectRequest,
        _user_code: str = Depends(_extract_user_code),
    ) -> Any:
        """收集视图定义（工作区模式，多轮合并）。"""
        try:
            if body.workspace_name:
                return platform.collect_view_to_workspace(
                    user_code=_user_code,
                    workspace_name=body.workspace_name,
                    view_code=body.view_code,
                    view_name=body.view_name,
                    view_desc=body.view_desc,
                    object_codes=body.object_codes,
                    object_relations=body.object_relations,
                    fields=body.fields,
                )
            return platform.collect_view_info(
                user_code=_user_code,
                view_code=body.view_code,
                view_name=body.view_name,
                view_desc=body.view_desc,
                object_codes=body.object_codes,
                object_relations=body.object_relations,
                fields=body.fields,
            )
        except Exception as exc:
            logger.exception("view/collect 失败")
            return {"ok": False, "error": str(exc)}

    @router.post("/view/delete")
    async def view_delete(
        body: WorkspaceViewDeleteRequest,
        _user_code: str = Depends(_extract_user_code),
    ) -> Any:
        """删除工作区视图。"""
        try:
            if body.workspace_name:
                return platform.delete_workspace_view(
                    user_code=_user_code,
                    workspace_name=body.workspace_name,
                    view_code=body.view_code,
                )
            return platform.delete_build_view(
                user_code=_user_code,
                view_code=body.view_code,
            )
        except Exception as exc:
            logger.exception("view/delete 失败")
            return {"ok": False, "error": str(exc)}

    @router.get("/view/list")
    async def view_list(
        workspace_name: str,
        _user_code: str = Depends(_extract_user_code),
    ) -> Any:
        """列出工作区所有视图。"""
        try:
            return platform.list_workspace_views(
                user_code=_user_code, workspace_name=workspace_name
            )
        except Exception as exc:
            logger.exception("view/list 失败")
            return {"ok": False, "error": str(exc)}

    @router.get("/view/{view_code}")
    async def view_get(
        view_code: str,
        workspace_name: str,
        _user_code: str = Depends(_extract_user_code),
    ) -> Any:
        """获取视图完整定义。"""
        try:
            return platform.get_workspace_view(
                user_code=_user_code,
                workspace_name=workspace_name,
                view_code=view_code,
            )
        except Exception as exc:
            logger.exception("view/get 失败")
            return {"ok": False, "error": str(exc)}

    # ═══════════════════════════════════════════════════════════════════════
    # Action 管理
    # ═══════════════════════════════════════════════════════════════════════

    @router.post("/object/collect-action")
    async def object_collect_action(
        body: CollectActionRequest,
        _user_code: str = Depends(_extract_user_code),
    ) -> Any:
        """保存 Action 脚本和元数据。"""
        try:
            return platform.collect_action(
                user_code=_user_code,
                workspace_name=body.workspace_name,
                entity_code=body.entity_code,
                action_code=body.action_code,
                action_name=body.action_name,
                script=body.script,
                params=body.params,
                action_desc=body.action_desc,
                action_type=body.action_type,
                permission_roles=body.permission_roles,
                object_references=body.object_references,
            )
        except Exception as exc:
            logger.exception("object/collect-action 失败")
            return {"ok": False, "error": str(exc)}

    @router.post("/object/delete-action")
    async def object_delete_action(
        body: DeleteActionRequest,
        _user_code: str = Depends(_extract_user_code),
    ) -> Any:
        """删除 Action。"""
        try:
            return platform.delete_workspace_action(
                user_code=_user_code,
                workspace_name=body.workspace_name,
                entity_code=body.entity_code,
                action_code=body.action_code,
            )
        except Exception as exc:
            logger.exception("object/delete-action 失败")
            return {"ok": False, "error": str(exc)}

    @router.post("/object/run-action")
    async def object_run_action(
        body: RunActionRequest,
        _user_code: str = Depends(_extract_user_code),
    ) -> Any:
        """在沙箱中调试执行 Action 脚本。"""
        try:
            return await platform.run_action_debug(
                user_code=_user_code,
                workspace_name=body.workspace_name,
                entity_code=body.entity_code,
                action_code=body.action_code,
                params=body.params,
                script=body.script,
            )
        except Exception as exc:
            logger.exception("object/run-action 失败")
            return {"ok": False, "error": str(exc)}

    @router.get("/object/{entity_code}/actions")
    async def object_actions(
        entity_code: str,
        workspace_name: str,
        _user_code: str = Depends(_extract_user_code),
    ) -> Any:
        """列出对象的 Action 列表。"""
        try:
            return platform.list_workspace_actions(
                user_code=_user_code,
                workspace_name=workspace_name,
                entity_code=entity_code,
            )
        except Exception as exc:
            logger.exception("object/actions 失败")
            return {"ok": False, "error": str(exc)}

    @router.get("/object/{entity_code}/action/{action_code}")
    async def object_action_detail(
        entity_code: str,
        action_code: str,
        workspace_name: str,
        _user_code: str = Depends(_extract_user_code),
    ) -> Any:
        """获取 Action 详情（含脚本）。"""
        try:
            return platform.get_workspace_action(
                user_code=_user_code,
                workspace_name=workspace_name,
                entity_code=entity_code,
                action_code=action_code,
            )
        except Exception as exc:
            logger.exception("object/action/detail 失败")
            return {"ok": False, "error": str(exc)}

    # ═══════════════════════════════════════════════════════════════════════
    # SDK
    # ═══════════════════════════════════════════════════════════════════════

    @router.get("/{workspace_name}/sdk/{entity_code}")
    async def workspace_sdk(
        workspace_name: str,
        entity_code: str,
        _user_code: str = Depends(_extract_user_code),
    ) -> Any:
        """获取对象生成的 SDK 源代码。"""
        try:
            return platform.get_workspace_sdk(
                user_code=_user_code,
                workspace_name=workspace_name,
                entity_code=entity_code,
            )
        except Exception as exc:
            logger.exception("workspace/sdk 失败")
            return {"ok": False, "error": str(exc)}

    return router
