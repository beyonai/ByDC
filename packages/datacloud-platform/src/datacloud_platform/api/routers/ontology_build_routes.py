"""Ontology Manager API — 个人本体管理 REST 接口（factory pattern）。

将 OntologyBuildMixin 的核心能力暴露为 HTTP API，供 skills 脚本通过服务发现调用。

端点：
    POST /api/v1/ontology-manager/object/collect
    POST /api/v1/ontology-manager/object/submit
    POST /api/v1/ontology-manager/object/delete

    POST /api/v1/ontology-manager/view/collect
    POST /api/v1/ontology-manager/view/submit
    POST /api/v1/ontology-manager/view/delete

    POST /api/v1/ontology-manager/term-types/list
    POST /api/v1/ontology-manager/term-types/values

所有接口均支持通过请求体传入 ``base_id``，空则回落至平台默认本体库。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from datacloud_platform.platform import DatacloudPlatform

logger = logging.getLogger(__name__)


# ── FastAPI Dependency: header → user_code ─────────────────────────────────


def _extract_user_code(request: Request) -> str:
    """从 HTTP header 提取用户标识，不再写 os.environ。"""
    return request.headers.get("X-User-Code", "")


# ── Pydantic 模型 ──────────────────────────────────────────────────────────


class ObjectCollectRequest(BaseModel):
    entity_code: str = Field(alias="entity_code")
    session_id: str = Field(default="", alias="session_id")
    entity_name: str = Field(default="", alias="entity_name")
    entity_desc: str = Field(default="", alias="entity_desc")
    kb_id: str = Field(default="", alias="kb_id")
    kb_directory: str = Field(default="", alias="kb_directory")
    base_id: str = Field(default="", alias="base_id")
    fields: list[dict[str, Any]] | None = Field(default=None, alias="fields")


class ObjectSubmitRequest(BaseModel):
    entity_code: str = Field(alias="entity_code")
    session_id: str = Field(default="", alias="session_id")
    base_id: str = Field(default="", alias="base_id")


class ObjectDeleteRequest(BaseModel):
    entity_code: str = Field(..., min_length=1, alias="entity_code")
    base_id: str = Field(default="", alias="base_id")


class ViewCollectRequest(BaseModel):
    view_code: str = Field(alias="view_code")
    session_id: str = Field(default="", alias="session_id")
    view_name: str = Field(default="", alias="view_name")
    view_desc: str = Field(default="", alias="view_desc")
    base_id: str = Field(default="", alias="base_id")
    object_codes: list[str] | None = Field(default=None, alias="object_codes")
    object_relations: list[dict[str, Any]] | None = Field(
        default=None, alias="object_relations"
    )
    fields: list[dict[str, Any]] | None = Field(default=None, alias="fields")


class ViewSubmitRequest(BaseModel):
    view_code: str = Field(alias="view_code")
    session_id: str = Field(default="", alias="session_id")
    base_id: str = Field(default="", alias="base_id")


class ViewDeleteRequest(BaseModel):
    view_code: str = Field(..., min_length=1, alias="view_code")
    base_id: str = Field(default="", alias="base_id")


class TermTypesListRequest(BaseModel):
    keyword: str = Field(default="", alias="keyword")
    base_id: str = Field(default="", alias="base_id")


class TermTypesValuesRequest(BaseModel):
    term_type_code: str = Field(..., min_length=1, alias="term_type_code")
    keyword: str = Field(default="", alias="keyword")
    base_id: str = Field(default="", alias="base_id")


# ── Factory ────────────────────────────────────────────────────────────────


def create_ontology_build_routes(platform: DatacloudPlatform) -> APIRouter:
    """创建本体构建路由。

    Args:
        platform: 已配置的 DatacloudPlatform 实例。

    Returns:
        APIRouter with prefix ``/api/v1/ontology-manager``。
    """
    router = APIRouter(prefix="/api/v1/ontology-manager", tags=["Ontology Manager"])

    # ── 对象管理 ──────────────────────────────────────────────────────────

    @router.post("/object/collect")
    async def object_collect(
        body: ObjectCollectRequest,
        request: Request,
        _user_code: str = Depends(_extract_user_code),
    ) -> Any:
        """收集本体对象信息（多轮）。"""
        user_code = (
            _user_code or body.fields[0].get("_user_code", "") if body.fields else ""
        )
        try:
            return platform.collect_object_info(
                user_code=user_code,
                entity_code=body.entity_code,
                session_id=body.session_id,
                entity_name=body.entity_name,
                entity_desc=body.entity_desc,
                fields=body.fields,
                kb_id=body.kb_id,
                kb_directory=body.kb_directory,
                base_id=body.base_id,
            )
        except Exception as exc:
            logger.exception("object/collect 失败")
            return {"ok": False, "error": str(exc)}

    @router.post("/object/submit")
    async def object_submit(
        body: ObjectSubmitRequest,
        _user_code: str = Depends(_extract_user_code),
    ) -> Any:
        """提交本体对象。"""
        try:
            return platform.submit_object(
                user_code=_user_code,
                entity_code=body.entity_code,
                session_id=body.session_id,
                base_id=body.base_id,
            )
        except Exception as exc:
            logger.exception("object/submit 失败")
            return {"ok": False, "error": str(exc)}

    @router.post("/object/delete")
    async def object_delete(
        body: ObjectDeleteRequest,
        _user_code: str = Depends(_extract_user_code),
    ) -> Any:
        """删除本体对象。"""
        try:
            return platform.delete_build_object(
                user_code=_user_code,
                entity_code=body.entity_code,
                base_id=body.base_id,
            )
        except Exception as exc:
            logger.exception("object/delete 失败")
            return {"ok": False, "error": str(exc)}

    # ── 视图管理 ──────────────────────────────────────────────────────────

    @router.post("/view/collect")
    async def view_collect(
        body: ViewCollectRequest,
        _user_code: str = Depends(_extract_user_code),
    ) -> Any:
        """收集本体视图信息（多轮）。"""
        try:
            return platform.collect_view_info(
                user_code=_user_code,
                view_code=body.view_code,
                session_id=body.session_id,
                view_name=body.view_name,
                view_desc=body.view_desc,
                object_codes=body.object_codes,
                object_relations=body.object_relations,
                fields=body.fields,
                base_id=body.base_id,
            )
        except Exception as exc:
            logger.exception("view/collect 失败")
            return {"ok": False, "error": str(exc)}

    @router.post("/view/submit")
    async def view_submit(
        body: ViewSubmitRequest,
        _user_code: str = Depends(_extract_user_code),
    ) -> Any:
        """提交本体视图。"""
        try:
            return platform.submit_view(
                user_code=_user_code,
                view_code=body.view_code,
                session_id=body.session_id,
                base_id=body.base_id,
            )
        except Exception as exc:
            logger.exception("view/submit 失败")
            return {"ok": False, "error": str(exc)}

    @router.post("/view/delete")
    async def view_delete(
        body: ViewDeleteRequest,
        _user_code: str = Depends(_extract_user_code),
    ) -> Any:
        """删除本体视图。"""
        try:
            return platform.delete_build_view(
                user_code=_user_code,
                view_code=body.view_code,
                base_id=body.base_id,
            )
        except Exception as exc:
            logger.exception("view/delete 失败")
            return {"ok": False, "error": str(exc)}

    # ── 术语查询 ──────────────────────────────────────────────────────────

    @router.post("/term-types/list")
    async def term_types_list(body: TermTypesListRequest) -> Any:
        """查询可绑定的 LIST_TERM / DICT_TERM 术语类型。"""
        try:
            result = platform.list_bindable_term_types(
                keyword=body.keyword,
                base_id=body.base_id,
            )
            return {"ok": True, "data": result}
        except Exception as exc:
            logger.exception("term-types/list 失败")
            return {"ok": False, "error": str(exc)}

    @router.post("/term-types/values")
    async def term_types_values(body: TermTypesValuesRequest) -> Any:
        """查询指定术语类型下的术语值。"""
        try:
            result = platform.get_term_type_values(
                term_type_code=body.term_type_code,
                keyword=body.keyword,
                base_id=body.base_id,
            )
            return {"ok": True, "data": result}
        except Exception as exc:
            logger.exception("term-types/values 失败")
            return {"ok": False, "error": str(exc)}

    return router
