"""Ontology Manager API — 个人本体管理 REST 接口。

端点（workspace 模式，以 workspace_name 为核心）：
    POST /api/v1/ontology-manager/workspace/init
    GET  /api/v1/ontology-manager/workspace/{workspace_name}
    POST /api/v1/ontology-manager/workspace/batch-submit

    POST /api/v1/ontology-manager/object/collect
    POST /api/v1/ontology-manager/object/collect-action
    POST /api/v1/ontology-manager/object/run-action
    POST /api/v1/ontology-manager/object/delete
    GET  /api/v1/ontology-manager/object/list
    GET  /api/v1/ontology-manager/object/{entity_code}
    GET  /api/v1/ontology-manager/object/{entity_code}/fields
    GET  /api/v1/ontology-manager/object/{entity_code}/actions
    GET  /api/v1/ontology-manager/object/{entity_code}/action/{action_code}

    POST /api/v1/ontology-manager/view/collect
    POST /api/v1/ontology-manager/view/delete
    GET  /api/v1/ontology-manager/view/list
    GET  /api/v1/ontology-manager/view/{view_code}

    GET  /api/v1/ontology-manager/workspace/{workspace_name}/sdk/{entity_code}

    POST /api/v1/ontology-manager/term-types/list
    POST /api/v1/ontology-manager/term-types/values
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)

router = APIRouter()


# ── 内部辅助 ──────────────────────────────────────────────────────────────────


def _with_env(body: dict, request: Request) -> dict:
    """提取并注入环境变量，返回纯净参数。"""
    env_map: dict[str, str] = {}
    token = request.headers.get("Beyond-Token") or request.headers.get(
        "Authorization", ""
    ).removeprefix("Bearer ")
    user_code = request.headers.get("X-User-Code", "")
    if token:
        env_map["BEYOND_TOKEN"] = token
    if user_code:
        env_map["USER_CODE"] = user_code
    env_map.update(body.get("_env", {}))
    for k, v in env_map.items():
        if v:
            os.environ[k] = v
    return {k: v for k, v in body.items() if k != "_env"}


def _user_code(request: Request) -> str:
    uc = request.headers.get("X-User-Code", "")
    return uc or os.environ.get("USER_CODE", "")


def _get_wfm(user_code: str, workspace_name: str):
    from datacloud_knowledge.ingestion.workspace_manager import (
        WorkspaceFileManager,  # type: ignore[import-untyped]
    )

    return WorkspaceFileManager(user_code, workspace_name)


# ── 旧版 Session 辅助（保持向下兼容） ────────────────────────────────────────


def _init_discovery_redis() -> None:
    from by_framework.common.redis_client import init_redis  # type: ignore[import-untyped]

    init_redis(
        host=os.getenv("DATACLOUD_GATEWAY_REDIS_HOST", os.getenv("REDIS_HOST", "localhost")),
        port=int(os.getenv("DATACLOUD_GATEWAY_REDIS_PORT", os.getenv("REDIS_PORT", "6379"))),
        db=int(os.getenv("DATACLOUD_GATEWAY_REDIS_DATABASE", os.getenv("REDIS_DATABASE", "0"))),
        password=os.getenv("DATACLOUD_GATEWAY_REDIS_PASSWORD", os.getenv("REDIS_PASSWORD")) or None,
        username=os.getenv("DATACLOUD_GATEWAY_REDIS_USERNAME", os.getenv("REDIS_USERNAME")) or None,
    )


def _get_session():
    from datacloud_knowledge.ingestion.ontology_build import (
        OntologyBuildSession,  # type: ignore[import-untyped]
    )

    return OntologyBuildSession()


# ── Workspace 管理 ────────────────────────────────────────────────────────────


@router.get("/workspace/list")
async def workspace_list(request: Request):
    """列出当前用户所有工作区及待提交摘要。"""
    uc = _user_code(request)
    if not uc:
        return {"ok": False, "error": "缺少用户标识，请在 X-User-Code header 中传入"}
    try:
        from datacloud_knowledge.ingestion.workspace_manager import (  # type: ignore[import-untyped]
            _storage_root,
            list_user_workspaces,
        )

        storage_root = str(_storage_root())
        logger.info("workspace/list user_code=%s storage_root=%s", uc, storage_root)
        workspaces = list_user_workspaces(uc)
        return {"ok": True, "workspaces": workspaces, "total": len(workspaces)}
    except Exception as exc:
        logger.exception("workspace/list 失败 user_code=%s", uc)
        return {"ok": False, "error": str(exc)}


@router.post("/workspace/init")
async def workspace_init(body: dict, request: Request):
    """初始化工作区。

    Body:
        {
            "workspace_name": "travel_reimbursement",
            "workspace_desc": "差旅报销工作区"
        }
    """
    params = _with_env(body, request)
    uc = _user_code(request)
    workspace_name: str = params.get("workspace_name", "").strip()
    if not workspace_name:
        return {"ok": False, "error": "workspace_name 不能为空"}
    if not uc:
        return {"ok": False, "error": "缺少用户标识，请在 X-User-Code header 中传入"}
    try:
        wfm = _get_wfm(uc, workspace_name)
        state = wfm.init(workspace_desc=params.get("workspace_desc", ""))
        return {"ok": True, "workspace_name": workspace_name, "state": state}
    except Exception as exc:
        logger.exception("workspace/init 失败")
        return {"ok": False, "error": str(exc)}


@router.post("/workspace/delete")
async def workspace_delete(body: dict, request: Request):
    """删除工作区（⚠️ 删除整个工作区目录，不可逆）。

    只删除本地工作区文件，不删除已提交到本体库的 OWL 数据。
    如需同时清理已提交的对象/视图，请先分别调用 object/delete 和 view/delete。

    Body:
        {
            "workspace_name": "travel_reimbursement",
        }
    """
    params = _with_env(body, request)
    uc = _user_code(request)
    workspace_name: str = params.get("workspace_name", "").strip()

    if not workspace_name:
        return {"ok": False, "error": "workspace_name 不能为空"}
    if not uc:
        return {"ok": False, "error": "缺少用户标识"}

    try:
        wfm = _get_wfm(uc, workspace_name)
        existed = wfm.delete_workspace()
        return {"ok": True, "workspace_name": workspace_name, "existed": existed}
    except Exception as exc:
        logger.exception("workspace/delete 失败")
        return {"ok": False, "error": str(exc)}


@router.get("/workspace/{workspace_name}")
async def workspace_get(workspace_name: str, request: Request):
    """查询工作区状态（含所有对象和视图摘要）。"""
    uc = _user_code(request)
    if not uc:
        return {"ok": False, "error": "缺少用户标识"}
    try:
        wfm = _get_wfm(uc, workspace_name)
        state = wfm.get_workspace_state()
        return {"ok": True, **state}
    except FileNotFoundError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("workspace/get 失败")
        return {"ok": False, "error": str(exc)}


@router.post("/workspace/batch-submit")
async def workspace_batch_submit(body: dict, request: Request):
    """批量提交工作区中所有（或指定）对象和视图，并生成 SDK 文件。

    Body:
        {
            "workspace_name": "travel_reimbursement",
            "only": ["travel_application"],   # 可选，不填则全部提交
            "confirm_drop_columns": false      # 确认删除字段（有删列变更时必须为 true）
        }

    当某个已提交对象的字段有删除变更时，若 confirm_drop_columns 为 false，
    接口返回 need_confirm=true 并列出待删列，不执行 DDL，等待用户确认后重试。
    """
    params = _with_env(body, request)
    uc = _user_code(request)
    workspace_name: str = params.get("workspace_name", "").strip()
    if not workspace_name:
        return {"ok": False, "error": "workspace_name 不能为空"}
    if not uc:
        return {"ok": False, "error": "缺少用户标识"}

    only: list[str] = params.get("only") or []
    confirm_drop_columns: bool = bool(params.get("confirm_drop_columns", False))

    try:
        wfm = _get_wfm(uc, workspace_name)
        state = wfm.get_workspace_state()
    except FileNotFoundError as exc:
        return {"ok": False, "error": str(exc)}

    # ── 预检：收集所有需要删列的对象，若未确认则提前返回 ──────────────────────
    from datacloud_knowledge.ingestion.workspace_manager import (
        FieldDiff,  # type: ignore[import-untyped]
    )

    pending_drops: dict[str, list[str]] = {}  # entity_code → [col, ...]
    for obj_summary in state.get("objects", []):
        entity_code_pre: str = obj_summary["entity_code"]
        if only and entity_code_pre not in only:
            continue
        obj_status_pre: str = obj_summary.get("status", "draft")
        if obj_status_pre not in ("dirty",):
            continue
        fields_pre = wfm.load_fields(entity_code_pre)
        diff_pre: FieldDiff = wfm.diff_fields(entity_code_pre, fields_pre)
        if diff_pre.removed:
            pending_drops[entity_code_pre] = diff_pre.removed

    if pending_drops and not confirm_drop_columns:
        return {
            "ok": False,
            "need_confirm": True,
            "message": "以下对象存在字段删除变更，删除后数据不可恢复，请确认后重试（传 confirm_drop_columns: true）",
            "drop_columns": [
                {"entity_code": ec, "columns": cols} for ec, cols in pending_drops.items()
            ],
        }

    submitted_objects: list[str] = []
    submitted_views: list[str] = []
    failed: list[dict] = []
    sdk_files: dict[str, str] = {}

    # 提交对象
    for obj_summary in state.get("objects", []):
        entity_code: str = obj_summary["entity_code"]
        if only and entity_code not in only:
            continue
        obj_status: str = obj_summary.get("status", "draft")
        # submitted 且无变更：跳过
        if obj_status == "submitted":
            continue
        fields = wfm.load_fields(entity_code)
        defn = wfm._load_definition(entity_code) or {}  # noqa: SLF001
        entity_name: str = defn.get("entity_name", "")
        entity_desc: str = defn.get("entity_desc", "")

        try:
            from datacloud_data_sdk.ddl.table_manager import (  # type: ignore[import-untyped]
                add_columns,
                create_table,
                drop_columns,
            )

            if obj_status == "dirty":
                # 已提交对象：增量 DDL
                diff: FieldDiff = wfm.diff_fields(entity_code, fields)
                if diff.added:
                    add_columns(entity_code, diff.added)
                if diff.removed and confirm_drop_columns:
                    drop_columns(entity_code, diff.removed)
                if diff.type_changed:
                    # widening 变更：重建列（ADD + 数据迁移 + DROP 旧列）暂不支持，跳过并告警
                    for col, old_t, new_t in diff.type_changed:
                        logger.warning(
                            "类型变更暂不自动执行（需手动迁移）: entity=%s col=%s %s→%s",
                            entity_code,
                            col,
                            old_t,
                            new_t,
                        )
            else:
                # draft / failed：首次建表
                create_table(entity_code, fields)
            # 构建 OntologyBuildSession 临时状态并提交
            session = _get_session()
            # 加载工作区中定义的 Action，注入到 state 供 OWL 生成器使用
            action_codes = wfm._list_action_codes(entity_code)  # noqa: SLF001
            actions_for_owl: list[dict] = []
            for ac in action_codes:
                full = wfm.get_action_full(entity_code, ac) or {}
                actions_for_owl.append(full)

            session_state = {
                "entity_code": entity_code,
                "entity_name": entity_name,
                "entity_desc": entity_desc,
                "fields": fields,
                # 将 Action 元数据注入，_generate_object 会转换为 ActionConfig
                "actions": actions_for_owl,
                # term_sync 配置注入，_generate_object 会写入 OWL ext_property
                "term_sync": defn.get("term_sync") or {},
            }
            # 直接调用内部提交逻辑（注入 session 暂存状态后调 submit_object）
            from datacloud_knowledge.ingestion.workspace_store import (
                get_workspace_store,  # type: ignore[import-untyped]
            )

            store = get_workspace_store()
            tmp_key = f"{uc}:__batch__{entity_code}"
            store.save(tmp_key, session_state, ttl=300)

            submit_result: dict = session.submit_object(f"__batch__{entity_code}", session_id="")
            if not submit_result.get("ok", True):
                failed.append(
                    {"code": entity_code, "error": submit_result.get("error", "提交失败")}
                )
                wfm.update_entity_status(
                    entity_code, "failed", error=submit_result.get("error", "")
                )
                continue

            wfm.update_entity_status(
                entity_code,
                "submitted",
                resource_id=submit_result.get("resource_id", ""),
            )
            # 写字段快照（用于下次 diff 检测）
            wfm.save_submitted_field_snapshot(entity_code, fields)
            submitted_objects.append(entity_code)

            # 生成 SDK 文件
            from datacloud_knowledge.ingestion.sdk_generator import (
                generate_mapper_sdk,  # type: ignore[import-untyped]
            )

            sdk_content = generate_mapper_sdk(entity_code, entity_name, fields)
            wfm.save_sdk(entity_code, sdk_content)
            sdk_files[entity_code] = sdk_content

        except Exception as exc:
            logger.exception("提交对象 %s 失败", entity_code)
            failed.append({"code": entity_code, "error": str(exc)})
            wfm.update_entity_status(entity_code, "failed", error=str(exc))

    # 提交视图
    for view_summary in state.get("views", []):
        view_code: str = view_summary["view_code"]
        if only and view_code not in only:
            continue
        vdef = wfm.get_view_full(view_code) or {}

        try:
            session = _get_session()
            from datacloud_knowledge.ingestion.workspace_store import (
                get_workspace_store,  # type: ignore[import-untyped]
            )

            store = get_workspace_store()
            tmp_key = f"{uc}:__batch__{view_code}"
            view_state = {
                "view_code": view_code,
                "view_name": vdef.get("view_name", ""),
                "view_desc": vdef.get("view_desc", ""),
                "object_codes": vdef.get("object_codes", []),
                "object_relations": vdef.get("object_relations", []),
                "fields": vdef.get("fields", []),
            }
            store.save(tmp_key, view_state, ttl=300)

            submit_result = session.submit_view(f"__batch__{view_code}", session_id="")
            if not submit_result.get("ok", True):
                failed.append({"code": view_code, "error": submit_result.get("error", "提交失败")})
                wfm.update_view_status(view_code, "failed", error=submit_result.get("error", ""))
                continue

            wfm.update_view_status(
                view_code,
                "submitted",
                resource_id=submit_result.get("resource_id", ""),
            )
            submitted_views.append(view_code)

        except Exception as exc:
            logger.exception("提交视图 %s 失败", view_code)
            failed.append({"code": view_code, "error": str(exc)})
            wfm.update_view_status(view_code, "failed", error=str(exc))

    return {
        "ok": len(failed) == 0,
        "submitted_objects": submitted_objects,
        "submitted_views": submitted_views,
        "failed": failed,
        "sdk_files": sdk_files,
    }


# ── 对象字段收集 ──────────────────────────────────────────────────────────────


@router.post("/object/collect")
async def object_collect(body: dict, request: Request):
    """收集对象字段定义（工作区模式，多轮合并）。

    Body:
        {
            "workspace_name": "travel_reimbursement",
            "entity_code":    "travel_application",
            "entity_name":    "出差申请",
            "entity_desc":    "...",
            "fields":         [...]
        }

    若无 workspace_name 则退回旧 session 模式（向下兼容）。
    """
    params = _with_env(body, request)
    workspace_name: str = params.get("workspace_name", "").strip()

    if workspace_name:
        # 新工作区模式
        uc = _user_code(request)
        if not uc:
            return {"ok": False, "error": "缺少用户标识"}
        entity_code: str = params.get("entity_code", "").strip()
        if not entity_code:
            return {"ok": False, "error": "entity_code 不能为空"}

        # 格式校验
        fields = params.get("fields")
        if fields:
            from datacloud_knowledge.ingestion.ontology_build import (
                _validate_fields_format,  # type: ignore[import-untyped]
            )

            fmt_errors = _validate_fields_format(fields)
            if fmt_errors:
                return {"ok": False, "errors": fmt_errors}

        try:
            wfm = _get_wfm(uc, workspace_name)
            result = wfm.save_object(
                entity_code=entity_code,
                entity_name=params.get("entity_name", ""),
                entity_desc=params.get("entity_desc", ""),
                fields=fields,
                term_sync=params.get("term_sync") or None,
            )
            return result
        except Exception as exc:
            logger.exception("object/collect 失败")
            return {"ok": False, "error": str(exc)}

    # 旧 session 模式（向下兼容）
    try:
        result = _get_session().collect_object_info(
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
        logger.exception("object/collect(session) 失败")
        return {"ok": False, "error": str(exc)}


@router.post("/object/collect-action")
async def object_collect_action(body: dict, request: Request):
    """收集 Action 定义（脚本 + 参数 + 权限）。

    Body:
        {
            "workspace_name": "travel_reimbursement",
            "entity_code":    "travel_application",
            "action_code":    "submit_application",
            "action_name":    "提交申请",
            "action_type":    "OPERATION",
            "action_desc":    "...",
            "script":         "def execute(params): ...",
            "params":         [...],
            "permission_roles": ["employee"]
        }
    """
    params = _with_env(body, request)
    uc = _user_code(request)
    workspace_name: str = params.get("workspace_name", "").strip()
    entity_code: str = params.get("entity_code", "").strip()
    action_code: str = params.get("action_code", "").strip()
    action_name: str = params.get("action_name", "").strip()
    script: str = params.get("script", "").strip()
    # action_type: QUERY（查询类，只读数据）或 OPERATION（操作类，写入/修改数据）
    action_type: str = params.get("action_type", "OPERATION").strip().upper()
    if action_type not in ("QUERY", "OPERATION"):
        return {"ok": False, "error": "action_type 只能为 QUERY（查询类）或 OPERATION（操作类）"}

    if not workspace_name:
        return {"ok": False, "error": "workspace_name 不能为空"}
    if not uc:
        return {"ok": False, "error": "缺少用户标识"}
    if not entity_code:
        return {"ok": False, "error": "entity_code 不能为空"}
    if not action_code:
        return {"ok": False, "error": "action_code 不能为空"}
    if not action_name:
        return {"ok": False, "error": "action_name 不能为空"}
    if not script:
        return {"ok": False, "error": "script 不能为空"}

    action_params = params.get("params")
    if not action_params:
        return {"ok": False, "error": "params（入参/出参定义）不能为空"}

    try:
        wfm = _get_wfm(uc, workspace_name)
        file_path = wfm.save_action(
            entity_code=entity_code,
            action_code=action_code,
            action_name=action_name,
            script=script,
            params=action_params,
            action_desc=params.get("action_desc", ""),
            action_type=action_type,
            permission_roles=params.get("permission_roles"),
            object_references=params.get("object_references") or None,
        )
        return {
            "ok": True,
            "action_code": action_code,
            "action_type": action_type,
            "file": file_path,
        }
    except Exception as exc:
        logger.exception("object/collect-action 失败")
        return {"ok": False, "error": str(exc)}


@router.post("/object/run-action")
async def object_run_action(body: dict, request: Request):
    """在 debug.db 沙箱中执行 Action 脚本（调试用）。

    Body:
        {
            "workspace_name": "travel_reimbursement",
            "entity_code":    "travel_application",
            "action_code":    "submit_application",
            "params":         {"app_id": 1},
            "script":         "..."   # 可选，不填则读工作区文件
        }
    """
    params = _with_env(body, request)
    uc = _user_code(request)
    workspace_name: str = params.get("workspace_name", "").strip()
    entity_code: str = params.get("entity_code", "").strip()
    action_code: str = params.get("action_code", "").strip()

    if not workspace_name:
        return {"ok": False, "error": "workspace_name 不能为空"}
    if not uc:
        return {"ok": False, "error": "缺少用户标识"}
    if not entity_code:
        return {"ok": False, "error": "entity_code 不能为空"}
    if not action_code:
        return {"ok": False, "error": "action_code 不能为空"}
    if params.get("params") is None:
        return {"ok": False, "error": "params（Action 入参）不能为 null"}

    try:
        wfm = _get_wfm(uc, workspace_name)

        # 读取脚本：优先用调用方传入，否则从工作区文件读取
        script: str = params.get("script", "").strip()
        if not script:
            script = wfm.load_action_script(entity_code, action_code) or ""
        if not script:
            return {
                "ok": False,
                "error": f"脚本文件不存在：objects/{entity_code}/actions/{action_code}.py",
            }

        # 读取 action 元信息，从中获取 object_references 声明的跨对象依赖
        action_meta = wfm.load_action_meta(entity_code, action_code) or {}
        object_references: list[str] = action_meta.get("object_references", [])

        # 仅注入当前对象 + object_references 声明的对象字段
        # 不全量注入工作区所有对象，保证调试行为与生产一致：
        # 脚本里用了未声明的 mapper 会立刻 NameError
        scoped_codes = [entity_code, *object_references]
        scoped_fields: dict[str, list] = {
            code: wfm.load_fields(code)
            for code in scoped_codes
            if (wfm._root / "objects" / code / "fields.json").exists()  # noqa: SLF001
        }

        from datacloud_data_service.tools.debug_executor import run_action_debug

        result = await run_action_debug(
            script=script,
            params=params.get("params", {}),
            db_path=wfm.debug_db_path,
            all_fields=scoped_fields,
            user_code=uc,
        )
        return result
    except Exception as exc:
        logger.exception("object/run-action 失败")
        return {"ok": False, "error": str(exc)}


@router.post("/object/delete")
async def object_delete(body: dict, request: Request):
    """删除本体对象（同时删除工作区文件）。

    Body:
        {
            "workspace_name": "travel_reimbursement",  # 可选，有则同时删工作区文件
            "entity_code":    "...",
        }
    """
    params = _with_env(body, request)
    entity_code: str = params.get("entity_code", "").strip()
    workspace_name: str = params.get("workspace_name", "").strip()
    if not entity_code:
        return {"ok": False, "error": "entity_code 不能为空"}

    try:
        session = _get_session()
        session.delete_owl_scope("OBJECT", entity_code)

        uc = _user_code(request)
        if uc:
            try:
                from datacloud_data_sdk.ddl.table_manager import (
                    drop_table,  # type: ignore[import-untyped]
                )

                drop_table(entity_code, uc)
            except Exception:
                logger.warning("drop_table 失败，可能不影响主流程", exc_info=True)

        if uc and workspace_name:
            try:
                wfm = _get_wfm(uc, workspace_name)
                wfm.delete_object(entity_code)
            except Exception:
                logger.warning("工作区对象文件删除失败", exc_info=True)

        await _delete_resource_by_code(entity_code)
        return {"ok": True, "entity_code": entity_code}
    except Exception as exc:
        logger.exception("object/delete 失败")
        return {"ok": False, "error": str(exc)}


@router.post("/object/delete-action")
async def object_delete_action(body: dict, request: Request):
    """删除 Action（工作区文件）。

    Body:
        {
            "workspace_name": "travel_reimbursement",
            "entity_code":    "travel_application",
            "action_code":    "submit_application",
        }
    """
    params = _with_env(body, request)
    uc = _user_code(request)
    workspace_name: str = params.get("workspace_name", "").strip()
    entity_code: str = params.get("entity_code", "").strip()
    action_code: str = params.get("action_code", "").strip()

    if not workspace_name:
        return {"ok": False, "error": "workspace_name 不能为空"}
    if not uc:
        return {"ok": False, "error": "缺少用户标识"}
    if not entity_code:
        return {"ok": False, "error": "entity_code 不能为空"}
    if not action_code:
        return {"ok": False, "error": "action_code 不能为空"}

    try:
        wfm = _get_wfm(uc, workspace_name)
        existed = wfm.delete_action(entity_code, action_code)
        return {"ok": True, "action_code": action_code, "existed": existed}
    except Exception as exc:
        logger.exception("object/delete-action 失败")
        return {"ok": False, "error": str(exc)}


@router.get("/object/list")
async def object_list(request: Request, workspace_name: str = ""):
    """列出工作区所有对象。"""
    uc = _user_code(request)
    if not workspace_name or not uc:
        return {"ok": False, "error": "缺少 workspace_name 或用户标识"}
    try:
        wfm = _get_wfm(uc, workspace_name)
        objects = wfm.list_objects_summary()
        return {"ok": True, "objects": objects, "total": len(objects)}
    except Exception as exc:
        logger.exception("object/list 失败")
        return {"ok": False, "error": str(exc)}


@router.get("/object/{entity_code}")
async def object_get(entity_code: str, request: Request, workspace_name: str = ""):
    """获取对象完整定义（fields + actions 摘要）。"""
    uc = _user_code(request)
    if not workspace_name or not uc:
        return {"ok": False, "error": "缺少 workspace_name 或用户标识"}
    try:
        wfm = _get_wfm(uc, workspace_name)
        obj = wfm.get_object_full(entity_code)
        if obj is None:
            return {"ok": False, "error": f"对象 {entity_code!r} 不存在"}
        return {"ok": True, **obj}
    except Exception as exc:
        logger.exception("object/get 失败")
        return {"ok": False, "error": str(exc)}


@router.get("/object/{entity_code}/fields")
async def object_fields(entity_code: str, request: Request, workspace_name: str = ""):
    """获取对象字段列表。"""
    uc = _user_code(request)
    if not workspace_name or not uc:
        return {"ok": False, "error": "缺少 workspace_name 或用户标识"}
    try:
        wfm = _get_wfm(uc, workspace_name)
        fields = wfm.load_fields(entity_code)
        return {"ok": True, "entity_code": entity_code, "fields": fields, "total": len(fields)}
    except Exception as exc:
        logger.exception("object/fields 失败")
        return {"ok": False, "error": str(exc)}


@router.get("/object/{entity_code}/actions")
async def object_actions(entity_code: str, request: Request, workspace_name: str = ""):
    """获取对象 Action 摘要列表。"""
    uc = _user_code(request)
    if not workspace_name or not uc:
        return {"ok": False, "error": "缺少 workspace_name 或用户标识"}
    try:
        wfm = _get_wfm(uc, workspace_name)
        actions = wfm.list_actions_summary(entity_code)
        return {"ok": True, "entity_code": entity_code, "actions": actions, "total": len(actions)}
    except Exception as exc:
        logger.exception("object/actions 失败")
        return {"ok": False, "error": str(exc)}


@router.get("/object/{entity_code}/action/{action_code}")
async def action_get(
    entity_code: str, action_code: str, request: Request, workspace_name: str = ""
):
    """获取单个 Action 详情（含脚本）。"""
    uc = _user_code(request)
    if not workspace_name or not uc:
        return {"ok": False, "error": "缺少 workspace_name 或用户标识"}
    try:
        wfm = _get_wfm(uc, workspace_name)
        action = wfm.get_action_full(entity_code, action_code)
        if action is None:
            return {"ok": False, "error": f"Action {entity_code}/{action_code} 不存在"}
        return {"ok": True, **action}
    except Exception as exc:
        logger.exception("action/get 失败")
        return {"ok": False, "error": str(exc)}


# ── 视图管理 ──────────────────────────────────────────────────────────────────


@router.post("/view/collect")
async def view_collect(body: dict, request: Request):
    """收集视图定义（多轮合并）。

    Body:
        {
            "workspace_name":   "travel_reimbursement",
            "view_code":        "v_travel_full",
            "view_name":        "差旅全视图",
            "view_desc":        "...",
            "object_codes":     ["travel_application", "travel_expense"],
            "object_relations": [...],
            "fields":           [...]
        }

    若无 workspace_name 则退回旧 session 模式（向下兼容）。
    """
    params = _with_env(body, request)
    workspace_name: str = params.get("workspace_name", "").strip()

    if workspace_name:
        uc = _user_code(request)
        if not uc:
            return {"ok": False, "error": "缺少用户标识"}
        view_code: str = params.get("view_code", "").strip()
        view_name: str = params.get("view_name", "").strip()
        if not view_code:
            return {"ok": False, "error": "view_code 不能为空"}
        if not view_name:
            return {"ok": False, "error": "view_name 不能为空"}

        try:
            wfm = _get_wfm(uc, workspace_name)
            result = wfm.save_view(
                view_code=view_code,
                view_name=view_name,
                view_desc=params.get("view_desc", ""),
                object_codes=params.get("object_codes") or [],
                object_relations=params.get("object_relations") or [],
                fields=params.get("fields"),
            )
            return result
        except Exception as exc:
            logger.exception("view/collect 失败")
            return {"ok": False, "error": str(exc)}

    # 旧 session 模式
    try:
        result = _get_session().collect_view_info(
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
        logger.exception("view/collect(session) 失败")
        return {"ok": False, "error": str(exc)}


@router.post("/view/delete")
async def view_delete(body: dict, request: Request):
    """删除本体视图（同时删除工作区文件）。

    Body:
        {
            "workspace_name": "travel_reimbursement",  # 可选，有则同时删工作区文件
            "view_code": "...",
        }
    """
    params = _with_env(body, request)
    view_code: str = params.get("view_code", "").strip()
    workspace_name: str = params.get("workspace_name", "").strip()
    if not view_code:
        return {"ok": False, "error": "view_code 不能为空"}

    try:
        session = _get_session()
        session.delete_owl_scope("VIEW", view_code)

        uc = _user_code(request)
        if uc and workspace_name:
            try:
                wfm = _get_wfm(uc, workspace_name)
                wfm.delete_view(view_code)
            except Exception:
                logger.warning("工作区视图文件删除失败", exc_info=True)

        await _delete_resource_by_code(view_code)
        return {"ok": True, "view_code": view_code}
    except Exception as exc:
        logger.exception("view/delete 失败")
        return {"ok": False, "error": str(exc)}


@router.get("/view/list")
async def view_list(request: Request, workspace_name: str = ""):
    """列出工作区所有视图。"""
    uc = _user_code(request)
    if not workspace_name or not uc:
        return {"ok": False, "error": "缺少 workspace_name 或用户标识"}
    try:
        wfm = _get_wfm(uc, workspace_name)
        views = wfm.list_views_summary()
        return {"ok": True, "views": views, "total": len(views)}
    except Exception as exc:
        logger.exception("view/list 失败")
        return {"ok": False, "error": str(exc)}


@router.get("/view/{view_code}")
async def view_get(view_code: str, request: Request, workspace_name: str = ""):
    """获取视图完整定义。"""
    uc = _user_code(request)
    if not workspace_name or not uc:
        return {"ok": False, "error": "缺少 workspace_name 或用户标识"}
    try:
        wfm = _get_wfm(uc, workspace_name)
        view = wfm.get_view_full(view_code)
        if view is None:
            return {"ok": False, "error": f"视图 {view_code!r} 不存在"}
        return {"ok": True, **view}
    except Exception as exc:
        logger.exception("view/get 失败")
        return {"ok": False, "error": str(exc)}


# ── SDK 文件获取 ──────────────────────────────────────────────────────────────


@router.get("/workspace/{workspace_name}/sdk/{entity_code}")
async def workspace_get_sdk(workspace_name: str, entity_code: str, request: Request):
    """获取已生成的 SDK 文件内容（batch-submit 后可用）。"""
    uc = _user_code(request)
    if not uc:
        return {"ok": False, "error": "缺少用户标识"}
    try:
        wfm = _get_wfm(uc, workspace_name)
        content = wfm.load_sdk(entity_code)
        if content is None:
            return {
                "ok": False,
                "error": f"SDK 文件不存在：{entity_code}_sdk.py，请先执行 batch-submit",
            }
        return {"ok": True, "entity_code": entity_code, "content": content}
    except Exception as exc:
        logger.exception("workspace/sdk 失败")
        return {"ok": False, "error": str(exc)}


# ── 术语查询 ──────────────────────────────────────────────────────────────────


@router.post("/term-types/list")
async def term_types_list(body: dict, request: Request):
    """查询可绑定的 LIST_TERM / DICT_TERM 术语类型。"""
    try:
        keyword: str = body.get("keyword", "")
        result = _get_session().list_bindable_term_types(keyword=keyword)
        return {"ok": True, "data": result}
    except Exception as exc:
        logger.exception("term-types/list 失败")
        return {"ok": False, "error": str(exc)}


@router.post("/term-types/values")
async def term_types_values(body: dict, request: Request):
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


# ── 旧版 session 提交（向下兼容） ──────────────────────────────────────────────


@router.post("/object/submit")
async def object_submit(body: dict, request: Request):
    """提交本体对象（旧 session 模式）。"""
    params = _with_env(body, request)
    try:
        result = _get_session().submit_object(
            entity_code=params.get("entity_code", ""),
            session_id=params.get("session_id", ""),
        )
        return result
    except Exception as exc:
        logger.exception("object/submit 失败")
        return {"ok": False, "error": str(exc)}


@router.post("/view/submit")
async def view_submit(body: dict, request: Request):
    """提交本体视图（旧 session 模式）。"""
    params = _with_env(body, request)
    try:
        result = _get_session().submit_view(
            view_code=params.get("view_code", ""),
            session_id=params.get("session_id", ""),
        )
        return result
    except Exception as exc:
        logger.exception("view/submit 失败")
        return {"ok": False, "error": str(exc)}


# ── 内部辅助（服务发现下架资源） ─────────────────────────────────────────────


async def _delete_resource_by_code(resource_code: str) -> None:
    """通过服务发现下架本体资源。"""

    from by_framework.core.discovery import DiscoveryClient  # type: ignore[import-untyped]
    from by_framework.util.discovery_http_client import (
        DiscoveryHttpClient,  # type: ignore[import-untyped]
    )
    from by_framework.util.http_client import RetryConfig  # type: ignore[import-untyped]
    from redis.asyncio import Redis as AsyncRedis  # type: ignore[import-untyped]

    service_name = os.environ.get("BE_DOMAINNAME", "").strip()
    if not service_name:
        raise ValueError("BE_DOMAINNAME 环境变量未配置")

    token = os.environ.get("BEYOND_TOKEN", "")
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if token:
        headers["Beyond-Token"] = token

    _redis = AsyncRedis(
        host=os.getenv("DATACLOUD_GATEWAY_REDIS_HOST", os.getenv("REDIS_HOST", "localhost")),
        port=int(os.getenv("DATACLOUD_GATEWAY_REDIS_PORT", os.getenv("REDIS_PORT", "6379"))),
        db=int(os.getenv("DATACLOUD_GATEWAY_REDIS_DATABASE", os.getenv("REDIS_DATABASE", "0"))),
        password=os.getenv("DATACLOUD_GATEWAY_REDIS_PASSWORD", os.getenv("REDIS_PASSWORD"))
        or None,
        username=os.getenv("DATACLOUD_GATEWAY_REDIS_USERNAME", os.getenv("REDIS_USERNAME"))
        or None,
        decode_responses=True,
    )
    discovery_client = DiscoveryClient(redis_client=_redis, cache_interval=5)
    retry_config = RetryConfig(max_attempts=3, retry_on_status_codes={502, 503, 504})
    try:
        async with DiscoveryHttpClient(
            discovery_client, retry_config=retry_config, health_threshold_ms=-1
        ) as client:
            response = await client.post(
                service_name,
                "/byaiService/tool/deleteResourceByCodeAndOwnerType",
                headers=headers,
                json={"resourceCode": resource_code, "ownerType": "personal"},
            )
    finally:
        await discovery_client.close()
        await _redis.aclose()

    resp_body: dict = response.data if isinstance(response.data, dict) else {}
    if not response.is_success or resp_body.get("code", 0) != 0:
        raise RuntimeError(
            f"下架失败 HTTP {response.status_code}: {resp_body.get('msg', resp_body)}"
        )
