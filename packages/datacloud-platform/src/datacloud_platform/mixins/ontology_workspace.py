"""OntologyWorkspaceMixin — 工作区模式本体管理编排层。

组合 WorkspaceFileManager（持久化） + OntologyBackend（CRUD） +
TermBackend（术语写入） + SceneServiceMixin（场景管理） +
SDK Generator（代码生成） + TableManager（DDL）。

与 OntologyBuildMixin（session 模式，Redis 暂存）独立共存，
提供基于文件系统持久化的工作区开发流水线。
"""

from __future__ import annotations

import logging
from typing import Any

from datacloud_platform.models.action import Action, ActionParam
from datacloud_platform.models.object_type import ObjectType
from datacloud_platform.models.property import Property, TermMeta
from datacloud_platform.models.relation import Relation
from datacloud_platform.models.view import View, ViewProperty

logger = logging.getLogger(__name__)


class OntologyWorkspaceMixin:
    """工作区模式本体管理编排层。

    依赖协议（通过 DatacloudPlatform 多继承满足）：
      - _HasOntologyBackend: 对象/视图 CRUD + 场景管理
      - _HasTermBackend: 内联 term_values 写入术语库
      - SceneServiceMixin: create_object_with_scene / create_view_with_scene
      - _default_base_id(): 默认 base_id 解析
    """

    # ── 内部辅助 ──────────────────────────────────────────────────────────────

    @staticmethod
    def _get_wfm(user_code: str, workspace_name: str) -> Any:
        """工厂方法：每次返回新的 WorkspaceFileManager 实例。"""
        from datacloud_knowledge.ingestion.workspace_manager import (
            WorkspaceFileManager,
        )

        return WorkspaceFileManager(user_code, workspace_name)

    # ── 工作区 CRUD ──────────────────────────────────────────────────────────

    def workspace_init(
        self,
        *,
        user_code: str,
        workspace_name: str,
        workspace_desc: str = "",
        object_codes: list[str] | None = None,
    ) -> dict[str, Any]:
        """初始化工作区目录和 workspace.json（幂等）。"""
        if not user_code:
            return {"ok": False, "error": "user_code 不能为空"}
        if not workspace_name.strip():
            return {"ok": False, "error": "workspace_name 不能为空"}
        try:
            wfm = self._get_wfm(user_code, workspace_name.strip())
            state = wfm.init(
                workspace_desc=workspace_desc.strip(),
                object_codes=object_codes or None,
            )
            return {
                "ok": True,
                "workspace_name": workspace_name.strip(),
                "state": state,
            }
        except Exception:
            logger.exception("workspace_init 失败: %s/%s", user_code, workspace_name)
            return {"ok": False, "error": f"初始化工作区失败: {workspace_name}"}

    def workspace_list(self, *, user_code: str) -> dict[str, Any]:
        """列出用户所有工作区及待提交摘要。"""
        if not user_code:
            return {"ok": False, "error": "user_code 不能为空"}
        try:
            from datacloud_knowledge.ingestion.workspace_manager import (
                list_user_workspaces,
                _storage_root,
            )

            storage_root = str(_storage_root())
            logger.debug(
                "workspace_list: user_code=%s storage_root=%s", user_code, storage_root
            )
            workspaces = list_user_workspaces(user_code)
            return {"ok": True, "workspaces": workspaces, "total": len(workspaces)}
        except Exception:
            logger.exception("workspace_list 失败: user_code=%s", user_code)
            return {"ok": False, "error": "获取工作区列表失败"}

    def workspace_get(self, *, user_code: str, workspace_name: str) -> dict[str, Any]:
        """查询工作区状态（含所有对象和视图摘要）。"""
        if not user_code:
            return {"ok": False, "error": "user_code 不能为空"}
        try:
            wfm = self._get_wfm(user_code, workspace_name)
            state = wfm.get_workspace_state()
            return {"ok": True, **state}
        except FileNotFoundError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception:
            logger.exception("workspace_get 失败: %s/%s", user_code, workspace_name)
            return {"ok": False, "error": "获取工作区状态失败"}

    def workspace_delete(
        self, *, user_code: str, workspace_name: str
    ) -> dict[str, Any]:
        """删除工作区目录（不可逆，只删文件，不删已提交的本体数据）。"""
        if not user_code:
            return {"ok": False, "error": "user_code 不能为空"}
        try:
            wfm = self._get_wfm(user_code, workspace_name)
            existed = wfm.delete_workspace()
            return {
                "ok": True,
                "workspace_name": workspace_name,
                "existed": existed,
            }
        except Exception:
            logger.exception("workspace_delete 失败: %s/%s", user_code, workspace_name)
            return {"ok": False, "error": "删除工作区失败"}

    # ── 工作区模式对象收集 ───────────────────────────────────────────────────

    def collect_object_to_workspace(
        self,
        *,
        user_code: str,
        workspace_name: str,
        entity_code: str,
        entity_name: str = "",
        entity_desc: str = "",
        fields: list[dict[str, Any]] | None = None,
        term_sync: dict[str, Any] | None = None,
        table_name: str | None = None,
    ) -> dict[str, Any]:
        """收集对象字段定义（工作区模式，多轮合并写入文件）。"""
        if not user_code:
            return {"ok": False, "error": "user_code 不能为空"}
        if not entity_code.strip():
            return {"ok": False, "error": "entity_code 不能为空"}

        if fields:
            from datacloud_knowledge.ingestion.ontology_build import (
                _validate_fields_format,
            )

            fmt_errors = _validate_fields_format(fields)
            if fmt_errors:
                return {"ok": False, "errors": fmt_errors}

        try:
            wfm = self._get_wfm(user_code, workspace_name)
            result: dict[str, Any] = wfm.save_object(
                entity_code=entity_code.strip(),
                entity_name=entity_name.strip(),
                entity_desc=entity_desc.strip(),
                fields=fields,
                term_sync=term_sync,
                table_name=table_name,
            )
            return result
        except Exception:
            logger.exception(
                "collect_object_to_workspace 失败: %s/%s/%s",
                user_code,
                workspace_name,
                entity_code,
            )
            return {"ok": False, "error": f"保存对象信息失败: {entity_code}"}

    def collect_view_to_workspace(
        self,
        *,
        user_code: str,
        workspace_name: str,
        view_code: str,
        view_name: str = "",
        view_desc: str = "",
        object_codes: list[str] | None = None,
        object_relations: list[dict[str, Any]] | None = None,
        fields: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """收集视图定义（工作区模式，多轮合并写入文件）。"""
        if not user_code:
            return {"ok": False, "error": "user_code 不能为空"}
        if not view_code.strip():
            return {"ok": False, "error": "view_code 不能为空"}

        try:
            wfm = self._get_wfm(user_code, workspace_name)
            result: dict[str, Any] = wfm.save_view(
                view_code=view_code.strip(),
                view_name=view_name.strip(),
                view_desc=view_desc.strip(),
                object_codes=object_codes,
                object_relations=object_relations,
                fields=fields,
            )
            return result
        except Exception:
            logger.exception(
                "collect_view_to_workspace 失败: %s/%s/%s",
                user_code,
                workspace_name,
                view_code,
            )
            return {"ok": False, "error": f"保存视图信息失败: {view_code}"}

    # ── 批量提交 ─────────────────────────────────────────────────────────────

    def workspace_batch_submit(
        self,
        *,
        user_code: str,
        workspace_name: str,
        base_id: str = "",
        only: list[str] | None = None,
        confirm_drop_columns: bool = False,
    ) -> dict[str, Any]:
        """批量提交工作区中所有对象和视图，并生成 SDK 文件。

        编排流程：
        1. 预检：检测字段删除变更，未确认时返回 need_confirm
        2. 对象：DDL（建表/增删列）→ ObjectType CRUD → 术语写入 → SDK 生成
        3. 视图：View CRUD → Relation 创建

        Args:
            user_code: 用户标识。
            workspace_name: 工作区名称。
            base_id: 目标 Base ID；为空时退回第一个注册的 Base。
            only: 可选，只提交指定的 entity_code 列表。
            confirm_drop_columns: 确认删除字段（有删列变更时必须为 True）。
        """
        only_codes = only or []

        # ── 1. 加载工作区状态 ──
        try:
            wfm = self._get_wfm(user_code, workspace_name)
            state = wfm.get_workspace_state()
        except FileNotFoundError as exc:
            return {"ok": False, "error": str(exc)}

        resolved_base_id: str = base_id or self._default_base_id()  # type: ignore[attr-defined]

        # ── 2. 预检：字段删除变更 ──
        pending_drops = self._precheck_column_drops(wfm, state, only_codes)
        if pending_drops and not confirm_drop_columns:
            return {
                "ok": False,
                "need_confirm": True,
                "message": (
                    "以下对象存在字段删除变更，删除后数据不可恢复，"
                    "请确认后重试（传 confirm_drop_columns: true）"
                ),
                "drop_columns": [
                    {"entity_code": ec, "columns": cols}
                    for ec, cols in pending_drops.items()
                ],
            }

        # ── 3. 提交对象 ──
        submitted_objects, submitted_views, failed, sdk_files = (
            self._batch_submit_objects(
                wfm,
                state,
                resolved_base_id,
                only_codes,
                confirm_drop_columns,
                user_code,
            )
        )

        # ── 4. 提交视图 ──
        view_submitted, view_failed = self._batch_submit_views(
            wfm, state, resolved_base_id, only_codes, user_code
        )
        submitted_views.extend(view_submitted)
        failed.extend(view_failed)

        return {
            "ok": len(failed) == 0,
            "submitted_objects": submitted_objects,
            "submitted_views": submitted_views,
            "failed": failed,
            "sdk_files": sdk_files,
        }

    # ── 内部：预检 ────────────────────────────────────────────────────────────

    @staticmethod
    def _precheck_column_drops(
        wfm: Any, state: dict[str, Any], only_codes: list[str]
    ) -> dict[str, list[str]]:
        """检测需要删列的对象，返回 {entity_code: [col, ...]}。"""
        pending: dict[str, list[str]] = {}
        from datacloud_knowledge.ingestion.workspace_manager import FieldDiff

        for obj_summary in state.get("objects", []):
            entity_code: str = obj_summary["entity_code"]
            if only_codes and entity_code not in only_codes:
                continue
            obj_status: str = obj_summary.get("status", "draft")
            if obj_status not in ("dirty",):
                continue
            fields = wfm.load_fields(entity_code)
            diff: FieldDiff = wfm.diff_fields(entity_code, fields)
            if diff.removed:
                pending[entity_code] = diff.removed
        return pending

    # ── 内部：批量提交对象 ───────────────────────────────────────────────────

    def _batch_submit_objects(
        self,
        wfm: Any,
        state: dict[str, Any],
        base_id: str,
        only_codes: list[str],
        confirm_drop_columns: bool,
        user_code: str,
    ) -> tuple[list[str], list[str], list[dict[str, Any]], dict[str, str]]:
        """提交对象：DDL → CRUD → 术语 → SDK → 状态更新。"""
        from datacloud_knowledge.ingestion.sdk_generator import generate_mapper_sdk

        submitted: list[str] = []
        failed: list[dict[str, Any]] = []
        sdk_files: dict[str, str] = {}

        # 幂等写入 personal_sqlite datasource（所有 DYNAMIC_TABLE 对象公用）
        self._ensure_personal_sqlite_datasource(base_id, user_code)

        for obj_summary in state.get("objects", []):
            entity_code: str = obj_summary["entity_code"]
            if only_codes and entity_code not in only_codes:
                continue
            obj_status: str = obj_summary.get("status", "draft")

            try:
                fields = wfm.load_fields(entity_code)
                defn = wfm._load_definition(entity_code) or {}  # noqa: SLF001
                entity_name: str = defn.get("entity_name", entity_code)
                entity_desc: str = defn.get("entity_desc", "")
                entity_source = "DYNAMIC_TABLE"
                table_name: str | None = defn.get("table_name") or entity_code

                # 与旧版 OWL generator 一致：若字段列表里没有 id，自动插入主键字段
                has_id = any(f.get("property_code", "").lower() == "id" for f in fields)
                if not has_id:
                    fields = [
                        {
                            "property_code": "id",
                            "property_name": "主键",
                            "data_type": "INTEGER",
                            "is_primary_key": True,
                        },
                        *fields,
                    ]

                if obj_status != "submitted":
                    # DDL
                    self._apply_ddl(
                        entity_code, fields, obj_status, wfm, confirm_drop_columns
                    )

                # 加载 Action 元数据（构建 ObjectType 和写术语库都需要）
                action_codes = wfm._list_action_codes(entity_code)  # noqa: SLF001
                actions_meta: list[dict[str, Any]] = [
                    full
                    for ac in action_codes
                    if (full := wfm.get_action_full(entity_code, ac) or {})
                ]
                term_sync_cfg: dict[str, Any] | None = defn.get("term_sync") or None

                # 构建 ObjectType（含 Actions + term_sync，确保写入 registry）
                obj = self._build_object_type(
                    entity_code,
                    entity_name,
                    entity_desc,
                    entity_source,
                    base_id,
                    fields,
                    table_name=table_name,
                    actions_meta=actions_meta,
                    term_sync=term_sync_cfg,
                    user_code=user_code,
                )

                # CRUD: 创建对象 + 加入场景
                from datacloud_platform.adapters.registry_sync import obj_camel_to_owl

                obj_dict = obj.model_dump(by_alias=True)
                obj_payload = obj_camel_to_owl(obj_dict)
                self.create_object_with_scene(base_id, obj_payload)  # type: ignore[attr-defined]

                # 把 actions 写入 ontology_actions 独立表
                _backend = self._ontology_for(base_id)  # type: ignore[attr-defined]
                for _action in obj.actions:
                    action_payload = _action.model_dump(by_alias=True)
                    action_payload["ownerType"] = "personal"
                    action_payload["owner_type"] = "personal"
                    action_payload["userCode"] = user_code
                    action_payload["user_code"] = user_code
                    try:
                        _backend.create_action(base_id, entity_code, action_payload)
                    except Exception:
                        logger.exception(
                            "batch_submit: action %s/%s 写入独立表失败",
                            entity_code,
                            _action.action_code,
                        )

                # 内联 term_values → 写术语库（含 field + action param 枚举）
                self._write_inline_terms(
                    base_id, entity_code, fields, actions=actions_meta
                )

                # SDK 生成
                sdk_content = generate_mapper_sdk(entity_code, entity_name, fields)
                wfm.save_sdk(entity_code, sdk_content)
                sdk_files[entity_code] = sdk_content

                # 状态更新
                wfm.update_entity_status(entity_code, "submitted")
                wfm.save_submitted_field_snapshot(entity_code, fields)

                submitted.append(entity_code)
                logger.info("batch_submit: 对象 %s 提交成功", entity_code)

            except Exception:
                logger.exception("batch_submit: 对象 %s 提交失败", entity_code)
                wfm.update_entity_status(entity_code, "failed")
                failed.append({"code": entity_code, "error": "对象提交失败"})

        return submitted, [], failed, sdk_files

    # ── 内部：DDL ─────────────────────────────────────────────────────────────

    @staticmethod
    def _apply_ddl(
        entity_code: str,
        fields: list[dict[str, Any]],
        obj_status: str,
        wfm: Any,
        confirm_drop_columns: bool,
    ) -> None:
        """根据对象状态执行 DDL：draft→建表，dirty→增量 DDL。"""
        from datacloud_data_sdk.ddl.table_manager import (
            add_columns,
            create_table,
            drop_columns,
        )
        from datacloud_knowledge.ingestion.workspace_manager import FieldDiff

        if obj_status == "dirty":
            diff: FieldDiff = wfm.diff_fields(entity_code, fields)
            if diff.added:
                add_columns(entity_code, diff.added)
            if diff.removed and confirm_drop_columns:
                drop_columns(entity_code, diff.removed)
            if diff.type_changed:
                for col, old_t, new_t in diff.type_changed:
                    logger.warning(
                        "类型变更暂不自动执行（需手动迁移）: entity=%s col=%s %s→%s",
                        entity_code,
                        col,
                        old_t,
                        new_t,
                    )
        else:
            # draft / failed: 首次建表
            create_table(entity_code, fields)

    # ── 内部：构建 ObjectType ─────────────────────────────────────────────────

    @staticmethod
    def _build_object_type(
        entity_code: str,
        entity_name: str,
        entity_desc: str,
        entity_source: str,
        base_id: str,
        fields: list[dict[str, Any]],
        *,
        table_name: str | None = None,
        actions_meta: list[dict[str, Any]] | None = None,
        term_sync: dict[str, Any] | None = None,
        user_code: str = "",
    ) -> ObjectType:
        """从工作区字段列表构建 ObjectType 模型。

        处理两种术语绑定方式：
        - term_type_code: 直接绑定已有术语类型
        - term_values: 内联枚举值，自动推导 term_type_code

        Args:
            actions_meta: Action 元数据列表（来自 wfm.get_action_full），
                嵌入 ObjectType.actions，确保写入 objects_registry.json 后
                生产 loader 能正常加载脚本。
            term_sync: 对象级术语同步配置 dict（来自 definition.json），
                作为 extra 字段嵌入，loader 通过 _parse_term_sync 读取。
        """
        properties: list[Property] = []
        for f in fields:
            prop_code = f.get("property_code", "")
            term_type_code = f.get("term_type_code", "")
            term_values = f.get("term_values") or []
            if term_values and not term_type_code:
                term_type_code = f"{entity_code}_{prop_code}"

            terminology = None
            if term_type_code:
                terminology = TermMeta(
                    termMasterType="",
                    termTypeCode=term_type_code,
                    termField=prop_code,
                )

            # source_column 优先取字段里显式指定的值，缺省回退到 property_code
            # 与旧版 OWL 一致：source_table_code=entity_code, source_column_code=col.name
            source_col = f.get("source_column") or f.get("sourceColumn") or prop_code
            is_pk = bool(f.get("is_primary_key", False))
            prop = Property(
                propertyName=f.get("property_name", prop_code),
                propertyCode=prop_code,
                propertyDesc=f.get("property_desc") or f.get("description", ""),
                dataType=f.get("data_type", "STRING"),
                isRequired=1 if f.get("is_required") else 0,
                terminology=terminology,
                sourceColumn=source_col,
                businessKey=1 if is_pk else 0,
            )
            prop_dict = prop.model_dump(by_alias=True)
            # Preserve raw extras that Property schema doesn't declare
            if f.get("ext_property"):
                prop_dict["ext_property"] = f["ext_property"]
            if f.get("term_values"):
                prop_dict["term_values"] = f["term_values"]
            properties.append(Property.model_validate(prop_dict))

        actions: list[Action] = [
            Action(
                actionCode=a.get("action_code", ""),
                actionName=a.get("action_name", ""),
                actionType=a.get("action_type", "OPERATION"),
                belongObjectCode=entity_code,
                actionDesc=a.get("action_desc", ""),
                script=a.get("script"),
                ownerType="personal",
                userCode=user_code or None,
                params=[
                    ActionParam(
                        paramCode=p.get("paramCode", p.get("param_code", "")),
                        paramName=p.get("paramName", p.get("param_name", "")),
                        paramType=p.get("paramType", p.get("param_type")),
                        isRequired=1 if p.get("required") else 0,
                        direction=p.get("direction"),
                        mappingPath=p.get("mappingPath", p.get("mapping_path")),
                    )
                    for p in a.get("params", [])
                ],
                object_references=a.get("object_references") or [],  # type: ignore[call-arg]
            )
            for a in (actions_meta or [])
            if a.get("action_code")
        ]

        extra: dict[str, object] = {"term_sync": term_sync} if term_sync else {}

        # DYNAMIC_TABLE 对象必须携带 source_config，与旧版 OWL 生成路径保持一致。
        # OWL 流程中 db_code 固定为 "personal_sqlite"，connector_type 为 "BYCLAW_SQL_EXECUTE"。
        # loader 从 source_config.alias 读取 datasource_alias，缺失会导致动作执行报错。
        if entity_source == "DYNAMIC_TABLE":
            extra["source_config"] = {
                "alias": "personal_sqlite",
                "db_type": "SQLITE",
                "datasource_id": None,
                "connector_type": "BYCLAW_SQL_EXECUTE",
            }

        return ObjectType(
            objectCode=entity_code,
            objectName=entity_name,
            objectDesc=entity_desc,
            objectSource=entity_source,
            ownerType="personal",
            userCode=user_code or None,
            baseId=base_id,
            tableName=table_name,
            properties=properties,
            actions=actions,
            **extra,  # type: ignore[arg-type]
        )

    # ── 内部：内联 term_values 写入术语库 ──────────────────────────────────────

    def _write_inline_terms(
        self,
        base_id: str,
        entity_code: str,
        fields: list[dict[str, Any]],
        *,
        actions: list[dict[str, Any]] | None = None,
    ) -> None:
        """将字段及 Action 参数的内联 term_values 写入术语库（TermBackend 路径）。

        对每个有 term_values 的字段或 action param：
        1. create_term_type() — 注册术语类型（DICT_TERM，幂等）
        2. create_term() — 逐个写入术语实例（幂等）
        """
        term_backend = self._term_for(base_id)  # type: ignore[attr-defined]

        # 收集所有需要写入的 (type_code, type_name, term_values) 三元组
        entries: list[tuple[str, str, list[dict[str, str]]]] = []

        for f in fields:
            raw_values = f.get("term_values") or []
            if not raw_values:
                continue
            prop_code = f.get("property_code", "")
            explicit_ttc = f.get("term_type_code", "")
            auto_ttc = explicit_ttc if explicit_ttc else f"{entity_code}_{prop_code}"
            prop_name = f.get("property_name", prop_code)
            term_values: list[dict[str, str]] = [
                v if isinstance(v, dict) else {"code": str(v), "name": str(v)}
                for v in raw_values
                if v
            ]
            if term_values:
                entries.append((auto_ttc, prop_name, term_values))

        for action_meta in actions or []:
            action_code = action_meta.get("action_code", "")
            for param in action_meta.get("params", []):
                raw_pv = param.get("term_values") or []
                if not raw_pv:
                    continue
                param_code = param.get("paramCode") or param.get("param_code", "")
                explicit_ttc = param.get("term_type_code", "")
                auto_ttc = (
                    explicit_ttc if explicit_ttc else f"{action_code}_{param_code}"
                )
                param_name = param.get("paramName") or param.get(
                    "param_name", param_code
                )
                param_values: list[dict[str, str]] = [
                    v if isinstance(v, dict) else {"code": str(v), "name": str(v)}
                    for v in raw_pv
                    if v
                ]
                if param_values:
                    entries.append((auto_ttc, param_name, param_values))

        if not entries:
            return

        for type_code, type_name, term_values in entries:
            try:
                term_backend.create_term_type(
                    term_type={
                        "typeCode": type_code,
                        "typeName": type_name,
                        "typeCategory": 2,  # DICT_TERM
                        "typeDesc": "",
                        "isBuiltin": False,
                    }
                )
            except Exception:
                logger.debug(
                    "term_type may already exist: %s", type_code, exc_info=True
                )

            for entry in term_values:
                value_code = entry.get("code", "")
                value_name = entry.get("name", value_code)
                if not value_code:
                    continue
                try:
                    term_backend.create_term(
                        term={
                            "termTypeCode": type_code,
                            "termName": value_name,
                            "termCode": value_code,
                            "libraryCode": "PERSONAL_LIB",
                            "domainCode": "PERSONAL_DOMAIN",
                        }
                    )
                except Exception:
                    logger.debug(
                        "term may already exist: %s/%s",
                        type_code,
                        value_code,
                        exc_info=True,
                    )

            logger.info(
                "_write_inline_terms: entity=%s ttc=%s count=%d",
                entity_code,
                type_code,
                len(term_values),
            )

    # ── 内部：确保 personal_sqlite datasource 已入库 ─────────────────────────

    def _ensure_personal_sqlite_datasource(self, base_id: str, user_code: str) -> None:
        """幂等写入 personal_sqlite datasource（DYNAMIC_TABLE 所有对象公用）。"""
        from datacloud_platform.models.datasource import Datasource, DbConnection

        ds = Datasource(
            db=[
                DbConnection(
                    dbId="personal_sqlite",
                    dbCode="personal_sqlite",
                    dbType="SQLITE",
                    dbParams={},
                )
            ],
            ownerType="personal",
            userCode=user_code or None,
        )
        try:
            backend = self._ontology_for(base_id)  # type: ignore[attr-defined]
            backend.create_datasource(base_id, ds)
            logger.info(
                "batch_submit: personal_sqlite datasource 写入成功 base_id=%s", base_id
            )
        except Exception:
            logger.exception(
                "batch_submit: personal_sqlite datasource 写入失败 base_id=%s", base_id
            )

    # ── 内部：批量提交视图 ───────────────────────────────────────────────────

    def _batch_submit_views(
        self,
        wfm: Any,
        state: dict[str, Any],
        base_id: str,
        only_codes: list[str],
        user_code: str,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """提交视图：View CRUD → Relation 创建。"""
        submitted: list[str] = []
        failed: list[dict[str, Any]] = []

        for view_summary in state.get("views", []):
            view_code: str = view_summary["view_code"]
            if only_codes and view_code not in only_codes:
                continue
            vdef = wfm.get_view_full(view_code) or {}
            if not vdef:
                continue

            try:
                # 构建 View
                view = View(
                    viewCode=view_code,
                    viewName=vdef.get("view_name", view_code),
                    description=vdef.get("view_desc", ""),
                    objectCodes=vdef.get("object_codes", []),
                    ownerType="personal",
                    userCode=user_code or None,
                    properties=[
                        ViewProperty(
                            propertyCode=f.get("property_code", ""),
                            propertyName=f.get(
                                "property_name", f.get("property_code", "")
                            ),
                            sourceObject=f.get("_source_object_code", ""),
                            sourceObjectProperty=f.get("property_code", ""),
                        )
                        for f in vdef.get("fields", [])
                    ],
                )

                # CRUD: 创建视图 + 加入场景
                self.create_view_with_scene(base_id, view)  # type: ignore[attr-defined]

                # 创建对象间关系
                for rel in vdef.get("object_relations", []):
                    relation = Relation(
                        relationCode=(
                            f"{rel.get('source_object_code', '')}_to_"
                            f"{rel.get('target_object_code', '')}"
                        ),
                        relationName=rel.get("relation_name", ""),
                        relationCardinality=rel.get("relation_type", "MANY_TO_ONE"),
                        sourceObjectCode=rel.get("source_object_code", ""),
                        targetObjectCode=rel.get("target_object_code", ""),
                        ownerType="personal",
                        userCode=user_code or None,
                    )
                    try:
                        self.create_relation(base_id, relation)  # type: ignore[attr-defined]
                    except Exception:
                        logger.exception("创建视图关系失败: %s", rel)

                wfm.update_view_status(view_code, "submitted")
                submitted.append(view_code)
                logger.info("batch_submit: 视图 %s 提交成功", view_code)

            except Exception:
                logger.exception("batch_submit: 视图 %s 提交失败", view_code)
                wfm.update_view_status(view_code, "failed")
                failed.append({"code": view_code, "error": "视图提交失败"})

        return submitted, failed

    # ── 工作区对象删除 ───────────────────────────────────────────────────────

    def delete_workspace_object(
        self,
        *,
        user_code: str,
        workspace_name: str,
        entity_code: str,
    ) -> dict[str, Any]:
        """删除工作区对象：删物理表 + 从场景移除 + 删工作区文件。"""
        if not entity_code.strip():
            return {"ok": False, "error": "entity_code 不能为空"}

        base_id: str = self._default_base_id()  # type: ignore[attr-defined]

        try:
            # 删物理表
            from datacloud_data_sdk.ddl.table_manager import drop_table

            drop_table(entity_code.strip(), user_code)

            # 从场景移除并删除 ontology 元数据
            self.delete_object_from_all_scenes(base_id, entity_code.strip())  # type: ignore[attr-defined]

            # 删工作区文件
            wfm = self._get_wfm(user_code, workspace_name)
            wfm.delete_object(entity_code.strip())

            return {"ok": True, "entity_code": entity_code.strip()}
        except Exception:
            logger.exception(
                "delete_workspace_object 失败: %s/%s/%s",
                user_code,
                workspace_name,
                entity_code,
            )
            return {"ok": False, "error": f"删除对象失败: {entity_code}"}

    def delete_workspace_view(
        self,
        *,
        user_code: str,
        workspace_name: str,
        view_code: str,
    ) -> dict[str, Any]:
        """删除工作区视图：从场景移除 + 删工作区文件。"""
        if not view_code.strip():
            return {"ok": False, "error": "view_code 不能为空"}

        base_id: str = self._default_base_id()  # type: ignore[attr-defined]

        try:
            self.delete_view_from_all_scenes(base_id, view_code.strip())  # type: ignore[attr-defined]

            wfm = self._get_wfm(user_code, workspace_name)
            wfm.delete_view(view_code.strip())

            return {"ok": True, "view_code": view_code.strip()}
        except Exception:
            logger.exception(
                "delete_workspace_view 失败: %s/%s/%s",
                user_code,
                workspace_name,
                view_code,
            )
            return {"ok": False, "error": f"删除视图失败: {view_code}"}
