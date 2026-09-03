"""OntologyWorkspaceMixin — 工作区模式本体管理编排层。

组合 WorkspaceFileManager（持久化） + OntologyBackend（CRUD） +
TermBackend（术语写入） + SceneServiceMixin（场景管理） +
SDK Generator（代码生成） + TableManager（DDL）。

与 OntologyBuildMixin（session 模式，Redis 暂存）独立共存，
提供基于文件系统持久化的工作区开发流水线。
"""

from __future__ import annotations

import os
import logging
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from datacloud_platform.enterprise_datasource import datasource_from_environment
from datacloud_platform.models.action import Action, ActionParam
from datacloud_platform.models.object_type import ObjectType
from datacloud_platform.models.property import Property, TermMeta
from datacloud_platform.models.relation import Relation
from datacloud_platform.models.view import View, ViewProperty
from datacloud_platform.publishing import (
    PublishConfigurationError,
    PublishContext,
    PublishTargetResolver,
)
from datacloud_platform.schema_manager import (
    EnterpriseSqlSchemaManager,
    PersonalSqliteSchemaManager,
    SqlAlchemyEnterpriseExecutor,
)
from datacloud_platform.workspace_template import (
    default_workspace_templates_root,
    materialize_workspace_template,
    select_workspace_templates,
)

logger = logging.getLogger(__name__)


def _action_param_term_binding(param: dict[str, Any]) -> dict[str, Any]:
    term_type_code = param.get("term_type_code") or param.get("termTypeCode")
    term_data_type = param.get("term_data_type") or param.get("termDataType")
    if not term_type_code or not term_data_type:
        return {}

    normalized_data_type = str(term_data_type).upper()
    master_type = {"DICT_TERM": "dict", "LIST_TERM": "list"}.get(normalized_data_type)
    result: dict[str, Any] = {
        "term_type_code": term_type_code,
        "term_data_type": term_data_type,
    }
    if master_type:
        result["termMeta"] = {
            "termTypeCode": term_type_code,
            "termField": "code",
            "termMasterType": master_type,
        }
    return result


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

    @staticmethod
    def _get_wfm_at_root(user_code: str, workspace_name: str, root: Path) -> Any:
        """创建使用隔离根目录的工作区管理器。"""
        from datacloud_knowledge.ingestion.workspace_manager import (
            WorkspaceFileManager,
        )

        return WorkspaceFileManager(user_code, workspace_name, root=root)

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

    def submit_workspace_templates(
        self,
        *,
        user_code: str,
        template_directory: str,
        is_personal: bool,
        is_sqlite: bool,
        base_id: str = "",
        tenant_id: str | None = None,
        confirm_scope_conversion: bool = False,
        reuse_target_tables: bool = True,
        confirm_drop_target_tables: bool = False,
        publish_id: str | None = None,
    ) -> dict[str, Any]:
        """扫描配置目录中的模板，创建并发布全部工作区。"""
        if not user_code.strip():
            return {"ok": False, "error": "user_code 不能为空"}

        storage_type = "sqlite" if is_sqlite else "database"
        normalized_user_code = user_code.strip()
        try:
            templates = select_workspace_templates(
                default_workspace_templates_root(), template_directory
            )
        except (FileNotFoundError, OSError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}
        if not templates:
            return {"ok": False, "error": "模板目录下没有可用的工作区模板"}

        results: list[dict[str, Any]] = []
        for template_root in templates:
            workspace_name = template_root.name
            try:
                with tempfile.TemporaryDirectory(
                    prefix="datacloud-template-publish-"
                ) as temporary_directory:
                    temporary_root = Path(temporary_directory) / workspace_name
                    wfm = self._get_wfm_at_root(
                        normalized_user_code, workspace_name, temporary_root
                    )
                    materialized = materialize_workspace_template(
                        template_root=template_root,
                        destination_root=wfm.root,
                        workspace_name=workspace_name,
                        user_code=normalized_user_code,
                        is_personal=is_personal,
                    )
                    result = self.workspace_batch_submit(
                        user_code=normalized_user_code,
                        workspace_name=workspace_name,
                        base_id=base_id,
                        owner_type="personal" if is_personal else "enterprise",
                        tenant_id=tenant_id,
                        confirm_scope_conversion=confirm_scope_conversion,
                        reuse_target_tables=reuse_target_tables,
                        confirm_drop_target_tables=confirm_drop_target_tables,
                        publish_id=publish_id,
                        storage_type=storage_type,
                        workspace_manager=wfm,
                    )
                results.append(
                    {
                        **result,
                        "template": template_root.name,
                        "workspace_name": workspace_name,
                        "object_codes": materialized.object_codes,
                        "action_codes": materialized.action_codes,
                    }
                )
            except (FileExistsError, FileNotFoundError, OSError, ValueError) as exc:
                logger.exception("工作区模板发布失败: %s", template_root.name)
                results.append(
                    {"ok": False, "template": template_root.name, "error": str(exc)}
                )

        succeeded = sum(result.get("ok") is True for result in results)
        return {
            "ok": succeeded == len(results),
            "is_personal": is_personal,
            "is_sqlite": is_sqlite,
            "template_directory": template_directory,
            "total": len(results),
            "succeeded": succeeded,
            "failed": len(results) - succeeded,
            "results": results,
        }

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
            raise

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
        owner_type: str = "personal",
        tenant_id: str | None = None,
        confirm_scope_conversion: bool = False,
        confirm_drop_target_tables: bool = False,
        publish_id: str | None = None,
        storage_type: str | None = None,
        workspace_manager: Any | None = None,
        reuse_target_tables: bool = False,
    ) -> dict[str, Any]:
        """按统一发布上下文批量提交工作区对象、Action、View 和 Relation。"""
        only_codes = only or []
        try:
            wfm = workspace_manager or self._get_wfm(user_code, workspace_name)
            state = wfm.get_workspace_state()
        except FileNotFoundError as exc:
            return {"ok": False, "error": str(exc)}

        resolved_base_id: str = base_id or self._default_base_id()  # type: ignore[attr-defined]
        active_publication = wfm.load_active_publication()
        try:
            context = PublishTargetResolver().resolve(
                owner_type=owner_type,
                user_code=user_code,
                tenant_id=tenant_id,
                base_id=resolved_base_id,
                publish_id=publish_id,
                active_publication=active_publication,
                storage_type=storage_type,
            )
        except PublishConfigurationError as exc:
            return {"ok": False, "code": exc.code, "error": str(exc)}

        selected_objects = [
            item["entity_code"]
            for item in state.get("objects", [])
            if not only_codes or item["entity_code"] in only_codes
        ]
        selected_views = [
            item["view_code"]
            for item in state.get("views", [])
            if not only_codes or item["view_code"] in only_codes
        ]
        historical_personal_publication = bool(
            not active_publication
            and context.owner_type == "enterprise"
            and any(
                item.get("status") in {"submitted", "dirty"}
                for item in state.get("objects", [])
                if not only_codes or item["entity_code"] in only_codes
            )
        )
        scope_conversion = historical_personal_publication or bool(
            active_publication
            and active_publication.get("owner_type") != context.owner_type
        )
        record: dict[str, Any] = {
            **context.to_dict(),
            "workspace_name": workspace_name,
            "status": "planned",
            "started_at": datetime.now(UTC).isoformat(),
            "scope_conversion": scope_conversion,
            "historical_personal_publication": historical_personal_publication,
            "source_table_retained": scope_conversion,
            "object_codes": selected_objects,
            "view_codes": selected_views,
            "operations": [],
        }
        wfm.save_publication(record)

        if scope_conversion and not confirm_scope_conversion:
            return {
                "ok": False,
                "need_confirm": True,
                "publish_id": context.publish_id,
                "code": "SCOPE_CONVERSION_CONFIRMATION_REQUIRED",
                "message": "发布归属将发生转换；来源表保留，目标实例表将重新创建且不迁移数据",
                "target": context.to_dict(),
                "objects": selected_objects,
            }

        pending_drops = self._precheck_column_drops(wfm, state, only_codes)
        if pending_drops and not confirm_drop_columns:
            return {
                "ok": False,
                "need_confirm": True,
                "publish_id": context.publish_id,
                "message": (
                    "以下对象存在字段删除变更，删除后数据不可恢复，"
                    "请确认后重试（传 confirm_drop_columns: true）"
                ),
                "drop_columns": [
                    {"entity_code": ec, "columns": cols}
                    for ec, cols in pending_drops.items()
                ],
            }

        try:
            schema_manager = self._schema_manager(context)
            target_collisions = (
                []
                if reuse_target_tables
                else self._precheck_target_table_collisions(
                    schema_manager,
                    state,
                    only_codes,
                    scope_conversion=scope_conversion,
                )
            )
        except Exception as exc:
            logger.exception("batch_submit: 发布数据源预检失败")
            record.update({"status": "failed", "error": str(exc)})
            wfm.save_publication(record)
            return {
                "ok": False,
                "publish_id": context.publish_id,
                "code": "PUBLISH_DATASOURCE_UNAVAILABLE",
                "error": str(exc),
            }

        if target_collisions and not confirm_drop_target_tables:
            record["target_table_collisions"] = target_collisions
            wfm.save_publication(record)
            return {
                "ok": False,
                "need_confirm": True,
                "publish_id": context.publish_id,
                "code": "DROP_TARGET_TABLE_CONFIRMATION_REQUIRED",
                "message": "目标端存在同名表；确认后将只删除目标表并重新创建空表",
                "target_tables": target_collisions,
            }

        submitted_objects, submitted_views, failed, sdk_files = (
            self._batch_submit_objects(
                wfm,
                state,
                only_codes,
                confirm_drop_columns,
                confirm_drop_target_tables,
                context,
                schema_manager,
                scope_conversion,
                record,
                reuse_target_tables=reuse_target_tables,
            )
        )

        view_submitted, view_failed = self._batch_submit_views(
            wfm, state, only_codes, context, record
        )
        submitted_views.extend(view_submitted)
        failed.extend(view_failed)

        record.update(
            {
                "status": "succeeded" if not failed else "failed",
                "finished_at": datetime.now(UTC).isoformat(),
                "submitted_objects": submitted_objects,
                "submitted_views": submitted_views,
                "failed": failed,
            }
        )
        wfm.save_publication(record)
        if not failed:
            wfm.activate_publication(record)

        return {
            "ok": len(failed) == 0,
            "publish_id": context.publish_id,
            "target": context.to_dict(),
            "submitted_objects": submitted_objects,
            "submitted_views": submitted_views,
            "failed": failed,
            "sdk_files": sdk_files,
        }

    def _schema_manager(
        self, context: PublishContext
    ) -> PersonalSqliteSchemaManager | EnterpriseSqlSchemaManager:
        if context.db_type == "SQLITE":
            return PersonalSqliteSchemaManager()
        datasource = self._upsert_enterprise_datasource(context)
        executor = SqlAlchemyEnterpriseExecutor.from_datasource(context, datasource)
        return EnterpriseSqlSchemaManager(context, executor)

    def _upsert_enterprise_datasource(self, context: PublishContext) -> dict[str, Any]:
        """Persist deployment DB credentials so Loader can resolve the object alias."""

        backend = self._ontology_for(context.base_id)  # type: ignore[attr-defined]
        backend.create_datasource(
            context.base_id,
            datasource_from_environment(context),
        )
        persisted: dict[str, Any] | None = backend.get_datasource_detail(
            context.datasource_alias, base_id=context.base_id
        )
        if persisted is None:
            raise RuntimeError(
                f"企业 Datasource {context.datasource_alias} 写入后无法读取"
            )
        return persisted

    @staticmethod
    def _precheck_target_table_collisions(
        schema_manager: PersonalSqliteSchemaManager | EnterpriseSqlSchemaManager,
        state: dict[str, Any],
        only_codes: list[str],
        *,
        scope_conversion: bool,
    ) -> list[str]:
        collisions: list[str] = []
        for item in state.get("objects", []):
            entity_code = item["entity_code"]
            if only_codes and entity_code not in only_codes:
                continue
            needs_recreate = scope_conversion or item.get("status", "draft") in {
                "draft",
                "failed",
            }
            if needs_recreate and schema_manager.target_table_exists(entity_code):
                schema = schema_manager.schema_name
                collisions.append(f"{schema}.{entity_code}" if schema else entity_code)
        return collisions

    # ── 内部：预检 ────────────────────────────────────────────────────────────

    @staticmethod
    def _precheck_column_drops(
        wfm: Any, state: dict[str, Any], only_codes: list[str]
    ) -> dict[str, list[str]]:
        """检测需要删列的对象，返回 {entity_code: [col, ...]}。"""
        pending: dict[str, list[str]] = {}
        from datacloud_knowledge.ingestion.workspace_manager import (
            FieldDiff,
            is_system_field_code,
        )

        for obj_summary in state.get("objects", []):
            entity_code: str = obj_summary["entity_code"]
            if only_codes and entity_code not in only_codes:
                continue
            obj_status: str = obj_summary.get("status", "draft")
            if obj_status not in ("dirty",):
                continue
            fields = wfm.load_fields(entity_code)
            diff: FieldDiff = wfm.diff_fields(entity_code, fields)
            removed = [code for code in diff.removed if not is_system_field_code(code)]
            if removed:
                pending[entity_code] = removed
        return pending

    # ── 内部：批量提交对象 ───────────────────────────────────────────────────

    def _batch_submit_objects(
        self,
        wfm: Any,
        state: dict[str, Any],
        only_codes: list[str],
        confirm_drop_columns: bool,
        confirm_drop_target_tables: bool,
        context: PublishContext,
        schema_manager: PersonalSqliteSchemaManager | EnterpriseSqlSchemaManager,
        scope_conversion: bool,
        publication_record: dict[str, Any],
        *,
        reuse_target_tables: bool = False,
    ) -> tuple[list[str], list[str], list[dict[str, Any]], dict[str, str]]:
        """提交对象：DDL → CRUD → 术语 → SDK → 状态更新。"""
        from datacloud_knowledge.ingestion.sdk_generator import generate_mapper_sdk

        submitted: list[str] = []
        failed: list[dict[str, Any]] = []
        sdk_files: dict[str, str] = {}

        if context.db_type == "SQLITE":
            self._ensure_personal_sqlite_datasource(context.base_id, context.user_code)

        for obj_summary in state.get("objects", []):
            entity_code: str = obj_summary["entity_code"]
            if only_codes and entity_code not in only_codes:
                continue
            obj_status: str = obj_summary.get("status", "draft")

            try:
                fields = wfm.load_fields(entity_code)
                defn = wfm._load_definition(entity_code) or {}  # noqa: SLF001
                entity_name: str = defn.get("entity_name", entity_code)
                entity_desc: str = (
                    defn.get("entity_desc", "")
                    + "。\n使用该对象时，需通过 query 参数传入完整的数据上下文。"
                )
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

                manage_target_table = scope_conversion or obj_status != "submitted"
                target_existed = False
                if reuse_target_tables:
                    target_existed = schema_manager.target_table_exists(entity_code)
                    if target_existed:
                        publication_record["operations"].append(
                            {"type": "REUSE_TARGET_TABLE", "object_code": entity_code}
                        )
                    else:
                        manage_target_table = True
                elif manage_target_table:
                    target_existed = schema_manager.target_table_exists(entity_code)

                if manage_target_table and not (reuse_target_tables and target_existed):
                    if (
                        obj_status == "dirty"
                        and not scope_conversion
                        and target_existed
                    ):
                        schema_manager.apply_incremental(
                            entity_code,
                            wfm.diff_fields(entity_code, fields),
                            confirm_drop_columns=confirm_drop_columns,
                        )
                        publication_record["operations"].append(
                            {"type": "ALTER_TARGET_TABLE", "object_code": entity_code}
                        )
                    else:
                        schema_manager.create_or_recreate(
                            entity_code,
                            fields,
                            recreate=True,
                            confirm_drop_target_table=confirm_drop_target_tables,
                        )
                        publication_record["operations"].append(
                            {
                                "type": "DROP_AND_CREATE_TARGET_TABLE"
                                if target_existed
                                else "CREATE_TARGET_TABLE",
                                "object_code": entity_code,
                                "source_table_retained": scope_conversion,
                            }
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
                    context.base_id,
                    fields,
                    table_name=table_name,
                    actions_meta=actions_meta,
                    term_sync=term_sync_cfg,
                    publish_context=context,
                )

                # CRUD: 创建对象 + 加入场景
                from datacloud_platform.adapters.registry_sync import obj_camel_to_owl

                obj_dict = obj.model_dump(by_alias=True)
                obj_payload = obj_camel_to_owl(obj_dict)
                self.create_object_with_scene(context.base_id, obj_payload)  # type: ignore[attr-defined]

                # 把 actions 写入 ontology_actions 独立表
                _backend = self._ontology_for(context.base_id)  # type: ignore[attr-defined]
                for _action in obj.actions:
                    action_payload = _action.model_dump(by_alias=True)
                    action_payload["ownerType"] = context.owner_type
                    action_payload["owner_type"] = context.owner_type
                    action_payload["userCode"] = (
                        context.user_code if context.owner_type == "personal" else None
                    )
                    action_payload["user_code"] = action_payload["userCode"]
                    action_payload["tenantId"] = context.tenant_id
                    action_payload["publishId"] = context.publish_id
                    _backend.create_action(context.base_id, entity_code, action_payload)

                # 内联 term_values → 写术语库（含 field + action param 枚举）
                self._write_inline_terms(
                    context.base_id, entity_code, fields, actions=actions_meta
                )

                # SDK 生成
                sdk_content = generate_mapper_sdk(entity_code, entity_name, fields)
                wfm.save_sdk(entity_code, sdk_content)
                sdk_files[entity_code] = sdk_content

                # 状态更新
                wfm.update_entity_status(entity_code, "submitted")
                wfm.save_submitted_field_snapshot(entity_code, fields)

                submitted.append(entity_code)
                publication_record["operations"].append(
                    {"type": "PUBLISH_OBJECT_METADATA", "object_code": entity_code}
                )
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
        publish_context: PublishContext,
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
                ownerType=publish_context.owner_type,
                userCode=(
                    publish_context.user_code
                    if publish_context.owner_type == "personal"
                    else None
                ),
                tenantId=publish_context.tenant_id,
                publishId=publish_context.publish_id,
                params=[
                    ActionParam(
                        paramCode=p.get("paramCode", p.get("param_code", "")),
                        paramName=p.get("paramName", p.get("param_name", "")),
                        paramType=p.get("paramType", p.get("param_type")),
                        isRequired=1 if p.get("required") else 0,
                        direction=p.get("direction"),
                        mappingPath=p.get("mappingPath", p.get("mapping_path")),
                        **_action_param_term_binding(p),
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
        # loader 从 source_config.alias 读取 datasource_alias，缺失会导致动作执行报错。
        if entity_source == "DYNAMIC_TABLE":
            extra["source_config"] = {
                "alias": publish_context.datasource_alias,
                "db_type": publish_context.db_type,
                "datasource_id": None,
                "connector_type": publish_context.connector_type,
                "schema": publish_context.schema_name,
            }
        extra["ext_property"] = {
            "tenant_id": publish_context.tenant_id,
            "publish_id": publish_context.publish_id,
        }

        return ObjectType(
            objectCode=entity_code,
            objectName=entity_name,
            objectDesc=entity_desc,
            objectSource=entity_source,
            ownerType=publish_context.owner_type,
            userCode=(
                publish_context.user_code
                if publish_context.owner_type == "personal"
                else None
            ),
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
                    library_id=base_id,
                    term_type={
                        "typeCode": type_code,
                        "typeName": type_name,
                        "typeCategory": 2,  # DICT_TERM
                        "typeDesc": "",
                        "isBuiltin": False,
                    },
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
                            "datasetId": base_id,
                            "libraryCode": base_id,
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
                    dbParams={
                        "user": "gaussdb",
                        "jdbc_url": f"jdbc:sqlite:{os.environ.get('FILE_STORAGE_MINIO_MOUNT_PATH', '')}/byclaw-datacloud/personal_object.db",
                        "password": "Admin@123",
                        "pool_max": 5,
                        "pool_min": 1,
                        "pool_timeout": 30,
                    },
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
        only_codes: list[str],
        context: PublishContext,
        publication_record: dict[str, Any],
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
                    ownerType=context.owner_type,
                    userCode=(
                        context.user_code if context.owner_type == "personal" else None
                    ),
                    tenantId=context.tenant_id,
                    publishId=context.publish_id,
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
                self.create_view_with_scene(context.base_id, view)  # type: ignore[attr-defined]

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
                        ownerType=context.owner_type,
                        userCode=(
                            context.user_code
                            if context.owner_type == "personal"
                            else None
                        ),
                        tenantId=context.tenant_id,
                        publishId=context.publish_id,
                    )
                    self.create_relation(context.base_id, relation)  # type: ignore[attr-defined]

                wfm.update_view_status(view_code, "submitted")
                submitted.append(view_code)
                publication_record["operations"].append(
                    {"type": "PUBLISH_VIEW_METADATA", "view_code": view_code}
                )
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
            self.delete_object_from_all_scenes(  # type: ignore[attr-defined]
                base_id, entity_code.strip()
            )

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
            self.delete_view_from_all_scenes(  # type: ignore[attr-defined]
                base_id, view_code.strip()
            )

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
