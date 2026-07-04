"""WorkspaceActionMixin — 工作区 Action 管理编排层。

组合 WorkspaceFileManager（文件持久化），提供 Action 脚本的定义、
存储、查询和删除能力。调试执行委托给 debug executor 组件。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class WorkspaceActionMixin:
    """工作区 Action 管理编排层。

    所有方法通过 WorkspaceFileManager 操作文件系统中的 Action 脚本和元数据。
    与 OntologyWorkspaceMixin 协作：Action 变更会触发对象状态 dirty 标记。
    """

    # ── 内部辅助 ──────────────────────────────────────────────────────────────

    @staticmethod
    def _get_wfm(user_code: str, workspace_name: str) -> Any:
        """工厂方法：每次返回新的 WorkspaceFileManager 实例。"""
        from datacloud_knowledge.ingestion.workspace_manager import (
            WorkspaceFileManager,
        )

        return WorkspaceFileManager(user_code, workspace_name)

    # ── Action 收集 ──────────────────────────────────────────────────────────

    def collect_action(
        self,
        *,
        user_code: str,
        workspace_name: str,
        entity_code: str,
        action_code: str,
        action_name: str,
        script: str,
        params: list[dict[str, Any]],
        action_desc: str = "",
        action_type: str = "OPERATION",
        permission_roles: list[str] | None = None,
        object_references: list[str] | None = None,
    ) -> dict[str, Any]:
        """保存 Action 脚本和元数据到工作区文件。

        Args:
            user_code: 用户标识。
            workspace_name: 工作区名称。
            entity_code: 所属对象编码。
            action_code: Action 编码（唯一）。
            action_name: Action 中文名称。
            script: Python 脚本内容（def execute(params): ...）。
            params: 参数列表 [{"paramCode": "...", "paramName": "...", ...}].
            action_desc: Action 描述。
            action_type: "QUERY"（查询，只读）或 "OPERATION"（操作，写入）。
            permission_roles: 权限角色列表（可选）。
            object_references: 脚本依赖的其他对象编码列表（可选）。
        """
        if not user_code:
            return {"ok": False, "error": "user_code 不能为空"}
        if not entity_code.strip():
            return {"ok": False, "error": "entity_code 不能为空"}
        if not action_code.strip():
            return {"ok": False, "error": "action_code 不能为空"}
        if not action_name.strip():
            return {"ok": False, "error": "action_name 不能为空"}

        try:
            wfm = self._get_wfm(user_code, workspace_name)
            path = wfm.save_action(
                entity_code=entity_code.strip(),
                action_code=action_code.strip(),
                action_name=action_name.strip(),
                script=script,
                params=params,
                action_desc=action_desc.strip(),
                action_type=action_type.upper(),
                permission_roles=permission_roles,
                object_references=object_references,
            )
            return {
                "ok": True,
                "action_code": action_code.strip(),
                "entity_code": entity_code.strip(),
                "path": path,
            }
        except Exception:
            logger.exception(
                "collect_action 失败: %s/%s/%s/%s",
                user_code,
                workspace_name,
                entity_code,
                action_code,
            )
            return {"ok": False, "error": f"保存 Action 失败: {action_code}"}

    # ── Action 删除 ──────────────────────────────────────────────────────────

    def delete_workspace_action(
        self,
        *,
        user_code: str,
        workspace_name: str,
        entity_code: str,
        action_code: str,
    ) -> dict[str, Any]:
        """删除 Action 脚本和元数据文件。"""
        if not entity_code.strip() or not action_code.strip():
            return {"ok": False, "error": "entity_code 和 action_code 不能为空"}

        try:
            wfm = self._get_wfm(user_code, workspace_name)
            deleted = wfm.delete_action(entity_code.strip(), action_code.strip())
            return {
                "ok": True,
                "entity_code": entity_code.strip(),
                "action_code": action_code.strip(),
                "deleted": deleted,
            }
        except Exception:
            logger.exception(
                "delete_action 失败: %s/%s/%s/%s",
                user_code,
                workspace_name,
                entity_code,
                action_code,
            )
            return {"ok": False, "error": f"删除 Action 失败: {action_code}"}

    # ── Action 查询 ──────────────────────────────────────────────────────────

    def list_workspace_actions(
        self,
        *,
        user_code: str,
        workspace_name: str,
        entity_code: str,
    ) -> dict[str, Any]:
        """列出对象的所有 Action 摘要（不含脚本内容）。"""
        if not entity_code.strip():
            return {"ok": False, "error": "entity_code 不能为空"}

        try:
            wfm = self._get_wfm(user_code, workspace_name)
            actions = wfm.list_actions_summary(entity_code.strip())
            return {"ok": True, "entity_code": entity_code.strip(), "actions": actions}
        except Exception:
            logger.exception(
                "list_actions 失败: %s/%s/%s",
                user_code,
                workspace_name,
                entity_code,
            )
            return {"ok": False, "error": f"查询 Action 列表失败: {entity_code}"}

    def get_workspace_action(
        self,
        *,
        user_code: str,
        workspace_name: str,
        entity_code: str,
        action_code: str,
    ) -> dict[str, Any]:
        """获取 Action 完整定义（含脚本内容）。"""
        if not entity_code.strip() or not action_code.strip():
            return {"ok": False, "error": "entity_code 和 action_code 不能为空"}

        try:
            wfm = self._get_wfm(user_code, workspace_name)
            full = wfm.get_action_full(entity_code.strip(), action_code.strip())
            if full is None:
                return {
                    "ok": False,
                    "error": f"Action 不存在: {entity_code}/{action_code}",
                }
            return {"ok": True, **full}
        except Exception:
            logger.exception(
                "get_action 失败: %s/%s/%s/%s",
                user_code,
                workspace_name,
                entity_code,
                action_code,
            )
            return {"ok": False, "error": f"查询 Action 失败: {action_code}"}

    # ── 工作区对象查询 ──────────────────────────────────────────────────────

    def list_workspace_objects(
        self,
        *,
        user_code: str,
        workspace_name: str,
    ) -> dict[str, Any]:
        """列出工作区所有对象摘要（不含字段详情）。"""
        try:
            wfm = self._get_wfm(user_code, workspace_name)
            objects = wfm.list_objects_summary()
            return {"ok": True, "objects": objects}
        except Exception:
            logger.exception(
                "list_workspace_objects 失败: %s/%s", user_code, workspace_name
            )
            return {"ok": False, "error": "查询对象列表失败"}

    def get_workspace_object(
        self,
        *,
        user_code: str,
        workspace_name: str,
        entity_code: str,
    ) -> dict[str, Any]:
        """获取对象完整定义（含字段和 Action 列表）。"""
        if not entity_code.strip():
            return {"ok": False, "error": "entity_code 不能为空"}

        try:
            wfm = self._get_wfm(user_code, workspace_name)
            full = wfm.get_object_full(entity_code.strip())
            if full is None:
                return {
                    "ok": False,
                    "error": f"对象不存在: {entity_code}",
                }
            return {"ok": True, **full}
        except Exception:
            logger.exception(
                "get_workspace_object 失败: %s/%s/%s",
                user_code,
                workspace_name,
                entity_code,
            )
            return {"ok": False, "error": f"查询对象失败: {entity_code}"}

    def get_workspace_object_fields(
        self,
        *,
        user_code: str,
        workspace_name: str,
        entity_code: str,
    ) -> dict[str, Any]:
        """获取对象字段定义列表。"""
        if not entity_code.strip():
            return {"ok": False, "error": "entity_code 不能为空"}

        try:
            wfm = self._get_wfm(user_code, workspace_name)
            fields = wfm.load_fields(entity_code.strip())
            return {"ok": True, "entity_code": entity_code.strip(), "fields": fields}
        except Exception:
            logger.exception(
                "get_workspace_object_fields 失败: %s/%s/%s",
                user_code,
                workspace_name,
                entity_code,
            )
            return {"ok": False, "error": f"查询对象字段失败: {entity_code}"}

    def list_workspace_views(
        self,
        *,
        user_code: str,
        workspace_name: str,
    ) -> dict[str, Any]:
        """列出工作区所有视图摘要。"""
        try:
            wfm = self._get_wfm(user_code, workspace_name)
            views = wfm.list_views_summary()
            return {"ok": True, "views": views}
        except Exception:
            logger.exception(
                "list_workspace_views 失败: %s/%s", user_code, workspace_name
            )
            return {"ok": False, "error": "查询视图列表失败"}

    def get_workspace_view(
        self,
        *,
        user_code: str,
        workspace_name: str,
        view_code: str,
    ) -> dict[str, Any]:
        """获取视图完整定义。"""
        if not view_code.strip():
            return {"ok": False, "error": "view_code 不能为空"}

        try:
            wfm = self._get_wfm(user_code, workspace_name)
            full = wfm.get_view_full(view_code.strip())
            if full is None:
                return {"ok": False, "error": f"视图不存在: {view_code}"}
            return {"ok": True, **full}
        except Exception:
            logger.exception(
                "get_workspace_view 失败: %s/%s/%s",
                user_code,
                workspace_name,
                view_code,
            )
            return {"ok": False, "error": f"查询视图失败: {view_code}"}

    def get_workspace_sdk(
        self,
        *,
        user_code: str,
        workspace_name: str,
        entity_code: str,
    ) -> dict[str, Any]:
        """获取对象生成的 SDK 源代码。"""
        if not entity_code.strip():
            return {"ok": False, "error": "entity_code 不能为空"}

        try:
            wfm = self._get_wfm(user_code, workspace_name)
            content = wfm.load_sdk(entity_code.strip())
            if content is None:
                return {
                    "ok": False,
                    "error": f"SDK 尚未生成: {entity_code}，请先执行 batch-submit",
                }
            return {"ok": True, "entity_code": entity_code.strip(), "sdk": content}
        except Exception:
            logger.exception(
                "get_workspace_sdk 失败: %s/%s/%s",
                user_code,
                workspace_name,
                entity_code,
            )
            return {"ok": False, "error": f"获取 SDK 失败: {entity_code}"}

    # ── Action 调试执行 ──────────────────────────────────────────────────────

    async def run_action_debug(
        self,
        *,
        user_code: str,
        workspace_name: str,
        entity_code: str,
        action_code: str,
        params: dict[str, Any] | None = None,
        user_name: str = "",
    ) -> dict[str, Any]:
        """在 SQLite 沙箱中调试执行 Action 脚本。

        从工作区文件读取脚本，在 debug.db 中执行。
        注入 Q/A/entity/mapper 命名空间，与正式执行环境一致。

        Args:
            user_code: 用户标识。
            workspace_name: 工作区名称。
            entity_code: 所属对象编码。
            action_code: Action 编码。
            params: 入参 dict。
            user_name: 用户显示名（注入 context.extras["user_name"]）。
        """
        if not entity_code.strip() or not action_code.strip():
            return {"ok": False, "error": "entity_code 和 action_code 不能为空"}

        try:
            wfm = self._get_wfm(user_code, workspace_name)

            # 读取脚本
            script = wfm.load_action_script(entity_code.strip(), action_code.strip())
            if script is None:
                return {
                    "ok": False,
                    "error": f"Action 脚本不存在: {entity_code}/{action_code}",
                }

            # 收集作用域内对象字段（当前对象 + object_references 依赖对象）
            action_meta = wfm.load_action_meta(entity_code.strip(), action_code.strip())
            object_refs: list[str] = (
                action_meta.get("object_references", []) if action_meta else []
            )
            scoped_codes = {entity_code.strip(), *object_refs}
            all_fields: dict[str, list[dict[str, Any]]] = {}
            for ec in scoped_codes:
                fields = wfm.load_fields(ec)
                if fields:
                    all_fields[ec] = fields

            # 调试执行
            from datacloud_platform.execution.workspace_executor import (
                WorkspaceScriptExecutor,
            )

            db_path = wfm.debug_db_path
            return await WorkspaceScriptExecutor.execute_debug(
                script=script,
                params=params or {},
                db_path=db_path,
                all_fields=all_fields,
                user_code=user_code,
                user_name=user_name,
            )
        except Exception:
            logger.exception(
                "run_action_debug 失败: %s/%s/%s/%s",
                user_code,
                workspace_name,
                entity_code,
                action_code,
            )
            return {"ok": False, "error": "调试执行失败"}
