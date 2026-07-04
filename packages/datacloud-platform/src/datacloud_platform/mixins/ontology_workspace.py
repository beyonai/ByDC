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
        self, *, user_code: str, workspace_name: str, workspace_desc: str = ""
    ) -> dict[str, Any]:
        """初始化工作区目录和 workspace.json（幂等）。"""
        if not user_code:
            return {"ok": False, "error": "user_code 不能为空"}
        if not workspace_name.strip():
            return {"ok": False, "error": "workspace_name 不能为空"}
        try:
            wfm = self._get_wfm(user_code, workspace_name.strip())
            state = wfm.init(workspace_desc=workspace_desc.strip())
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

        base_id: str = self._default_base_id()  # type: ignore[attr-defined]

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
        submitted_objects, submitted_views, failed = self._batch_submit_objects(
            wfm, state, base_id, only_codes, confirm_drop_columns
        )

        # ── 4. 提交视图 ──
        view_submitted, view_failed = self._batch_submit_views(
            wfm, state, base_id, only_codes
        )
        submitted_views.extend(view_submitted)
        failed.extend(view_failed)

        return {
            "ok": len(failed) == 0,
            "submitted_objects": submitted_objects,
            "submitted_views": submitted_views,
            "failed": failed,
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
    ) -> tuple[list[str], list[str], list[dict[str, Any]]]:
        """提交对象：DDL → CRUD → 术语 → SDK → 状态更新。"""
        from datacloud_knowledge.ingestion.sdk_generator import generate_mapper_sdk

        submitted: list[str] = []
        failed: list[dict[str, Any]] = []

        for obj_summary in state.get("objects", []):
            entity_code: str = obj_summary["entity_code"]
            if only_codes and entity_code not in only_codes:
                continue
            obj_status: str = obj_summary.get("status", "draft")
            if obj_status == "submitted":
                continue  # 无变更，跳过

            try:
                fields = wfm.load_fields(entity_code)
                defn = wfm._load_definition(entity_code) or {}  # noqa: SLF001
                entity_name: str = defn.get("entity_name", entity_code)
                entity_desc: str = defn.get("entity_desc", "")
                entity_source = "DYNAMIC_TABLE"

                # DDL
                self._apply_ddl(
                    entity_code, fields, obj_status, wfm, confirm_drop_columns
                )

                # 构建 ObjectType
                obj = self._build_object_type(
                    entity_code,
                    entity_name,
                    entity_desc,
                    entity_source,
                    base_id,
                    fields,
                )

                # CRUD: 创建对象 + 加入场景
                self.create_object_with_scene(base_id, obj)  # type: ignore[attr-defined]

                # 内联 term_values → 写术语库
                self._write_inline_terms(base_id, fields, entity_code)

                # SDK 生成
                sdk_content = generate_mapper_sdk(entity_code, entity_name, fields)
                wfm.save_sdk(entity_code, sdk_content)

                # 状态更新
                wfm.update_entity_status(entity_code, "submitted")
                wfm.save_submitted_field_snapshot(entity_code, fields)

                submitted.append(entity_code)
                logger.info("batch_submit: 对象 %s 提交成功", entity_code)

            except Exception:
                logger.exception("batch_submit: 对象 %s 提交失败", entity_code)
                wfm.update_entity_status(entity_code, "failed")
                failed.append({"code": entity_code, "error": "对象提交失败"})

        return submitted, [], failed

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
    ) -> ObjectType:
        """从工作区字段列表构建 ObjectType 模型。

        处理两种术语绑定方式：
        - term_type_code: 直接绑定已有术语类型
        - term_values: 内联枚举值，自动推导 term_type_code
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

            properties.append(
                Property(
                    propertyName=f.get("property_name", prop_code),
                    propertyCode=prop_code,
                    propertyDesc=f.get("property_desc", ""),
                    dataType=f.get("data_type", "STRING"),
                    terminology=terminology,
                )
            )

        return ObjectType(
            objectCode=entity_code,
            objectName=entity_name,
            objectDesc=entity_desc,
            objectSource=entity_source,
            baseId=base_id,
            properties=properties,
        )

    # ── 内部：内联 term_values 写入术语库 ──────────────────────────────────────

    def _write_inline_terms(
        self,
        base_id: str,
        fields: list[dict[str, Any]],
        entity_code: str,
    ) -> None:
        """将字段的内联 term_values 写入 TermBackend。

        对于每个有 term_values 的字段：
        1. 自动推导 term_type_code = {entity_code}_{property_code}
        2. create_term_type() 创建术语类型（DICT_TERM，category=2）
        3. create_term() 逐个写入术语实例
        """
        term_backend = self._term_for(base_id)  # type: ignore[attr-defined]

        for f in fields:
            raw_values = f.get("term_values") or []
            if not raw_values:
                continue

            prop_code = f.get("property_code", "")
            explicit_ttc = f.get("term_type_code", "")
            auto_ttc = explicit_ttc if explicit_ttc else f"{entity_code}_{prop_code}"
            prop_name = f.get("property_name", prop_code)

            # 规范化 term_values：支持字符串列表和 dict 列表
            term_values: list[dict[str, str]] = [
                v if isinstance(v, dict) else {"code": str(v), "name": str(v)}
                for v in raw_values
                if v
            ]
            if not term_values:
                continue

            try:
                # 创建术语类型（幂等，已存在时报错可忽略）
                term_backend.create_term_type(
                    term_type={
                        "typeCode": auto_ttc,
                        "typeName": prop_name,
                        "typeCategory": 2,  # DICT_TERM
                        "typeDesc": f"{entity_code}.{prop_code} 枚举值",
                        "isBuiltin": False,
                    }
                )
            except Exception:
                # 类型已存在时忽略
                logger.debug("term_type may already exist: %s", auto_ttc, exc_info=True)

            # 逐个写入术语实例
            for entry in term_values:
                value_code = entry.get("code", "")
                value_name = entry.get("name", value_code)
                if not value_code:
                    continue
                try:
                    term_backend.create_term(
                        term={
                            "termTypeCode": auto_ttc,
                            "termName": value_name,
                            "termCode": value_code,
                            "libraryCode": "PERSONAL_LIB",
                            "domainCode": "PERSONAL_DOMAIN",
                        }
                    )
                except Exception:
                    # 术语已存在时忽略
                    logger.debug(
                        "term may already exist: %s/%s",
                        auto_ttc,
                        value_code,
                        exc_info=True,
                    )

            logger.info(
                "_write_inline_terms: entity=%s field=%s ttc=%s count=%d",
                entity_code,
                prop_code,
                auto_ttc,
                len(term_values),
            )

    # ── 内部：批量提交视图 ───────────────────────────────────────────────────

    def _batch_submit_views(
        self,
        wfm: Any,
        state: dict[str, Any],
        base_id: str,
        only_codes: list[str],
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
