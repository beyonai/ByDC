"""Ontology Manager API — 个人本体管理 REST 接口。

将 datacloud_knowledge.ingestion.ontology_build.OntologyBuildSession 的核心能力
暴露为 HTTP API，供 skills 脚本通过服务发现调用。

端点：
    POST /api/v1/ontology-manager/object/collect
    POST /api/v1/ontology-manager/object/submit
    POST /api/v1/ontology-manager/object/delete

    POST /api/v1/ontology-manager/view/collect
    POST /api/v1/ontology-manager/view/submit
    POST /api/v1/ontology-manager/view/delete

    POST /api/v1/ontology-manager/term-types/list
    POST /api/v1/ontology-manager/term-types/values
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Ontology Manager"])


# ── session 工厂 ─────────────────────────────────────────────────────────────
#
# 不缓存 OntologyBuildSession 单例：submit_object / submit_view 内部通过
# _run_async_in_thread 在新线程的新 event loop 中执行 redis.asyncio 操作。
# 若复用同一个 Session，其 redis 连接已绑定到前次调用的 loop，下次调用时
# 出现 "Future attached to a different loop" / "Event loop is closed"。
# 每次请求创建新 Session，确保 asyncio 对象在正确的 loop 中初始化。


def _get_session() -> Any:
    """每次调用返回新的 OntologyBuildSession，避免跨 event loop 复用 asyncio 对象。"""
    from datacloud_knowledge.ingestion.ontology_build import OntologyBuildSession

    return OntologyBuildSession()


# ── 请求处理辅助 ─────────────────────────────────────────────────────────────


def _ensure_env(body: dict[str, Any]) -> None:
    """将 body 中的 env 字段注入当前进程环境变量（仅本次请求生效）。"""
    env: dict[str, str] = body.pop("_env", {}) or {}
    for key, value in env.items():
        if value:
            os.environ[key] = value


def _with_env(body: dict[str, Any], request: Request) -> dict[str, Any]:
    """提取并注入环境变量，返回纯净参数。"""
    env_map: dict[str, str] = {}
    # 从 header 提取 token / user_code
    token = request.headers.get("Beyond-Token") or request.headers.get(
        "Authorization", ""
    ).removeprefix("Bearer ")
    user_code = request.headers.get("X-User-Code", "")
    if token:
        env_map["BEYOND_TOKEN"] = token
    if user_code:
        env_map["USER_CODE"] = user_code
    # body 中的 _env 优先级最高（便于调试覆盖）
    env_map.update(body.get("_env", {}))
    if env_map:
        for k, v in env_map.items():
            if v:
                os.environ[k] = v
    # 返回去掉 _env 的纯净参数
    params = {k: v for k, v in body.items() if k != "_env"}
    return params


# ── 对象管理 ─────────────────────────────────────────────────────────────────


@router.post("/object/collect")
async def object_collect(body: dict[str, Any], request: Request) -> dict[str, Any]:
    """收集本体对象信息（多轮）。

    Body (与 skills stdin JSON 协议一致):
        {
            "entity_code": "...",
            "session_id": "...",
            "entity_name": "...",
            "entity_desc": "...",
            "kb_id": "...",
            "kb_directory": "...",
            "fields": [...],
            "_env": {"USER_CODE": "...", "BEYOND_TOKEN": "..."}
        }
    """
    params = _with_env(body, request)
    try:
        result: dict[str, Any] = _get_session().collect_object_info(
            entity_code=params.get("entity_code", ""),
            session_id=params.get("session_id", ""),
            entity_name=params.get("entity_name", ""),
            entity_desc=params.get("entity_desc", ""),
            fields=params.get("fields"),
            kb_id=params.get("kb_id", ""),
            kb_directory=params.get("kb_directory", ""),
        )
        return result
    except Exception as exc:
        logger.exception("object/collect 失败")
        return {"ok": False, "error": str(exc)}


@router.post("/object/submit")
async def object_submit(body: dict[str, Any], request: Request) -> dict[str, Any]:
    """提交本体对象。

    Body:
        {
            "entity_code": "...",
            "session_id": "...",
            "_env": {"USER_CODE": "...", "BEYOND_TOKEN": "..."}
        }
    """
    params = _with_env(body, request)
    try:
        result: dict[str, Any] = _get_session().submit_object(
            entity_code=params.get("entity_code", ""),
            session_id=params.get("session_id", ""),
        )
        return result
    except Exception as exc:
        logger.exception("object/submit 失败")
        return {"ok": False, "error": str(exc)}


@router.post("/object/delete")
async def object_delete(body: dict[str, Any], request: Request) -> dict[str, Any]:
    """删除本体对象。

    Body:
        {
            "entity_code": "...",
            "user_code": "...",
            "_env": {"BEYOND_TOKEN": "..."}
        }
    """
    params = _with_env(body, request)
    entity_code: str = params.get("entity_code", "").strip()
    if not entity_code:
        return {"ok": False, "error": "entity_code 不能为空"}

    try:
        # 1. 清除术语库
        _get_session().delete_owl_scope("OBJECT", entity_code)

        # 2. 建表删除
        user_code: str = params.get("user_code", "") or os.environ.get("USER_CODE", "")
        if user_code:
            from datacloud_data_sdk.ddl.table_manager import drop_table

            drop_table(entity_code, user_code)

        return {"ok": True, "entity_code": entity_code}
    except Exception as exc:
        logger.exception("object/delete 失败")
        return {"ok": False, "error": str(exc)}


# ── 视图管理 ─────────────────────────────────────────────────────────────────


@router.post("/view/collect")
async def view_collect(body: dict[str, Any], request: Request) -> dict[str, Any]:
    """收集本体视图信息（多轮）。

    Body:
        {
            "view_code": "...",
            "session_id": "...",
            "view_name": "...",
            "view_desc": "...",
            "object_codes": [...],
            "object_relations": [...],
            "fields": [...],
            "_env": {"USER_CODE": "..."}
        }
    """
    params = _with_env(body, request)
    try:
        result: dict[str, Any] = _get_session().collect_view_info(
            view_code=params.get("view_code", ""),
            session_id=params.get("session_id", ""),
            view_name=params.get("view_name", ""),
            view_desc=params.get("view_desc", ""),
            object_codes=params.get("object_codes"),
            object_relations=params.get("object_relations"),
            fields=params.get("fields"),
        )
        return result
    except Exception as exc:
        logger.exception("view/collect 失败")
        return {"ok": False, "error": str(exc)}


@router.post("/view/submit")
async def view_submit(body: dict[str, Any], request: Request) -> dict[str, Any]:
    """提交本体视图。

    Body:
        {
            "view_code": "...",
            "session_id": "...",
            "_env": {"USER_CODE": "...", "BEYOND_TOKEN": "..."}
        }
    """
    params = _with_env(body, request)
    try:
        result: dict[str, Any] = _get_session().submit_view(
            view_code=params.get("view_code", ""),
            session_id=params.get("session_id", ""),
        )
        return result
    except Exception as exc:
        logger.exception("view/submit 失败")
        return {"ok": False, "error": str(exc)}


@router.post("/view/delete")
async def view_delete(body: dict[str, Any], request: Request) -> dict[str, Any]:
    """删除本体视图。

    Body:
        {
            "view_code": "...",
            "_env": {"BEYOND_TOKEN": "..."}
        }
    """
    params = _with_env(body, request)
    view_code: str = params.get("view_code", "").strip()
    if not view_code:
        return {"ok": False, "error": "view_code 不能为空"}

    try:
        # 清除术语库
        _get_session().delete_owl_scope("VIEW", view_code)

        return {"ok": True, "view_code": view_code}
    except Exception as exc:
        logger.exception("view/delete 失败")
        return {"ok": False, "error": str(exc)}


# ── 术语查询 ─────────────────────────────────────────────────────────────────


@router.post("/term-types/list")
async def term_types_list(body: dict[str, Any], request: Request) -> dict[str, Any]:
    """查询可绑定的 LIST_TERM / DICT_TERM 术语类型。

    Body:
        {
            "keyword": ""   # 可选
        }
    """
    try:
        keyword: str = body.get("keyword", "")
        result = _get_session().list_bindable_term_types(keyword=keyword)
        return {"ok": True, "data": result}
    except Exception as exc:
        logger.exception("term-types/list 失败")
        return {"ok": False, "error": str(exc)}


@router.post("/term-types/values")
async def term_types_values(body: dict[str, Any], request: Request) -> dict[str, Any]:
    """查询指定术语类型下的术语值。

    Body:
        {
            "term_type_code": "task_status",
            "keyword": ""
        }
    """
    term_type_code: str = body.get("term_type_code", "").strip()
    if not term_type_code:
        return {"ok": False, "error": "term_type_code 不能为空"}
    keyword: str = body.get("keyword", "")

    try:
        result = _get_session().get_term_type_values(
            term_type_code=term_type_code,
            keyword=keyword,
        )
        return {"ok": True, "data": result}
    except Exception as exc:
        logger.exception("term-types/values 失败")
        return {"ok": False, "error": str(exc)}
