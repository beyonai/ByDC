"""工作区文件管理器 — 服务端持久化工作区。

工作区目录结构：
    {FILE_STORAGE_MINIO_MOUNT_PATH}/byclaw-datacloud/workspaces/{user_code}/{workspace_name}/
    ├── workspace.json
    ├── objects/
    │   └── {entity_code}/
    │       ├── definition.json
    │       ├── fields.json
    │       └── actions/
    │           ├── {action_code}.py
    │           └── {action_code}.json
    ├── views/
    │   └── {view_code}.json
    └── sdk/
        └── {entity_code}_sdk.py
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

logger = logging.getLogger(__name__)


# ── 字段变更描述 ──────────────────────────────────────────────────────────────


@dataclass
class FieldDiff:
    """字段变更摘要（对比上次提交快照与当前 fields.json）。"""

    added: list[dict[str, Any]] = field(default_factory=list)
    """新增字段（当前有、快照没有）。"""
    removed: list[str] = field(default_factory=list)
    """删除字段的 property_code 列表（快照有、当前没有）。"""
    type_changed: list[tuple[str, str, str]] = field(default_factory=list)
    """类型变更列表，每项为 (property_code, old_type, new_type)。"""

    def has_changes(self) -> bool:
        return bool(self.added or self.removed or self.type_changed)

    def has_destructive(self) -> bool:
        """是否包含不可自动执行的变更（删列或类型收窄）。"""
        return bool(self.removed or self._has_narrowing())

    def _has_narrowing(self) -> bool:
        """检测类型收窄：FLOAT→INTEGER、任意类型→STRING 之外的转换。"""
        _widening: set[tuple[str, str]] = {
            ("INTEGER", "FLOAT"),
            ("BOOLEAN", "INTEGER"),
            ("BOOLEAN", "FLOAT"),
        }
        return any((old, new) not in _widening for _, old, new in self.type_changed)


def _storage_root() -> Path:
    mount = os.environ.get("FILE_STORAGE_MINIO_MOUNT_PATH", "")
    if not mount:
        raise ValueError("FILE_STORAGE_MINIO_MOUNT_PATH 环境变量未设置")
    return Path(mount) / "byclaw-datacloud" / "workspaces"


class WorkspaceFileManager:
    """管理服务端工作区文件存储。"""

    def __init__(self, user_code: str, workspace_name: str) -> None:
        self._root = _storage_root() / user_code / workspace_name
        self._user_code = user_code
        self._workspace_name = workspace_name

    @property
    def root(self) -> Path:
        return self._root

    @property
    def debug_db_path(self) -> Path:
        return self._root / "debug.db"

    # ── workspace.json ────────────────────────────────────────────────────────

    def init(
        self,
        workspace_desc: str = "",
        object_codes: list[str] | None = None,
    ) -> dict[str, Any]:
        """初始化工作区目录和 workspace.json，幂等。

        Args:
            workspace_desc: 工作区描述。
            object_codes: 预声明对象编码列表，写入 draft 占位状态。
                已存在的工作区调用时追加新编码（不覆盖已有状态）。
        """
        self._root.mkdir(parents=True, exist_ok=True)
        ws_file = self._root / "workspace.json"
        if not ws_file.exists():
            state: dict[str, Any] = {
                "workspace_name": self._workspace_name,
                "objects": {},
                "views": {},
            }
            if workspace_desc:
                state["workspace_desc"] = workspace_desc
            ws_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

        if object_codes:
            raw = self._load_workspace_raw()
            objs: dict[str, Any] = raw.setdefault("objects", {})
            changed = False
            for code in object_codes:
                if code and code not in objs:
                    objs[code] = {"status": "draft"}
                    changed = True
            if changed:
                self._save_workspace_raw(raw)

        return self._load_workspace_raw()

    def _load_workspace_raw(self) -> dict[str, Any]:
        ws_file = self._root / "workspace.json"
        if not ws_file.exists():
            return {}
        return json.loads(ws_file.read_text(encoding="utf-8"))  # type: ignore[no-any-return]

    def _save_workspace_raw(self, state: dict[str, Any]) -> None:
        ws_file = self._root / "workspace.json"
        ws_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_workspace_state(self) -> dict[str, Any]:
        """获取工作区完整状态（含对象和视图摘要列表）。"""
        raw = self._load_workspace_raw()
        if not raw:
            raise FileNotFoundError(f"工作区 {self._workspace_name!r} 不存在，请先初始化")

        status_map: dict[str, Any] = raw.get("objects", {})
        view_status_map: dict[str, Any] = raw.get("views", {})

        objects_out: list[dict[str, Any]] = []
        for entity_code in self._list_entity_codes():
            defn = self._load_definition(entity_code) or {}
            obj_st = status_map.get(entity_code, {})
            objects_out.append(
                {
                    "entity_code": entity_code,
                    "entity_name": defn.get("entity_name", ""),
                    "entity_desc": defn.get("entity_desc", ""),
                    "status": obj_st.get("status", "draft"),
                    "resource_id": obj_st.get("resource_id", ""),
                    "action_count": len(self._list_action_codes(entity_code)),
                    "field_count": len(self.load_fields(entity_code)),
                }
            )

        views_out: list[dict[str, Any]] = []
        for view_code in self._list_view_codes():
            vdef = self._load_view_def(view_code) or {}
            view_st = view_status_map.get(view_code, {})
            views_out.append(
                {
                    "view_code": view_code,
                    "view_name": vdef.get("view_name", ""),
                    "view_desc": vdef.get("view_desc", ""),
                    "status": view_st.get("status", "draft"),
                    "resource_id": view_st.get("resource_id", ""),
                    "object_count": len(vdef.get("object_codes", [])),
                }
            )

        return {
            "workspace_name": raw.get("workspace_name", self._workspace_name),
            "workspace_desc": raw.get("workspace_desc", ""),
            "objects": objects_out,
            "views": views_out,
        }

    def update_entity_status(
        self,
        entity_code: str,
        status: str,
        resource_id: str = "",
        error: str = "",
    ) -> None:
        raw = self._load_workspace_raw()
        objs: dict[str, Any] = raw.setdefault("objects", {})
        existing: dict[str, Any] = objs.get(entity_code, {})
        entry: dict[str, Any] = {"status": status}
        # 保留 resource_id：submitted 时写入，其他状态沿用旧值
        if resource_id:
            entry["resource_id"] = resource_id
        elif existing.get("resource_id"):
            entry["resource_id"] = existing["resource_id"]
        if error:
            entry["error"] = error
        objs[entity_code] = entry
        self._save_workspace_raw(raw)

    def update_view_status(
        self,
        view_code: str,
        status: str,
        resource_id: str = "",
        error: str = "",
    ) -> None:
        raw = self._load_workspace_raw()
        views: dict[str, Any] = raw.setdefault("views", {})
        entry: dict[str, Any] = {"status": status}
        if resource_id:
            entry["resource_id"] = resource_id
        if error:
            entry["error"] = error
        views[view_code] = entry
        self._save_workspace_raw(raw)

    # ── object files ──────────────────────────────────────────────────────────

    def save_object(
        self,
        entity_code: str,
        entity_name: str = "",
        entity_desc: str = "",
        fields: list[dict[str, Any]] | None = None,
        term_sync: dict[str, Any] | None = None,
        table_name: str | None = None,
    ) -> dict[str, Any]:
        """合并写入对象的 definition.json 和 fields.json。"""
        obj_dir = self._root / "objects" / entity_code
        obj_dir.mkdir(parents=True, exist_ok=True)
        (obj_dir / "actions").mkdir(exist_ok=True)

        # definition.json — merge
        def_file = obj_dir / "definition.json"
        definition: dict[str, Any] = {"entity_code": entity_code}
        if def_file.exists():
            definition = json.loads(def_file.read_text(encoding="utf-8"))
        if entity_name:
            definition["entity_name"] = entity_name
        if entity_desc:
            definition["entity_desc"] = entity_desc
        if term_sync is not None:
            definition["term_sync"] = term_sync
        if table_name is not None:
            definition["table_name"] = table_name
        def_file.write_text(json.dumps(definition, ensure_ascii=False, indent=2), encoding="utf-8")

        # fields.json — merge by property_code
        merged_fields: list[dict[str, Any]] = []
        if fields is not None:
            existing_map: dict[str, dict[str, Any]] = {}
            fields_file = obj_dir / "fields.json"
            if fields_file.exists():
                existing_list: list[dict[str, Any]] = json.loads(
                    fields_file.read_text(encoding="utf-8")
                )
                existing_map = {f["property_code"]: f for f in existing_list}
            for f in fields:
                code = f.get("property_code", "")
                if code:
                    existing_map[code] = {**existing_map.get(code, {}), **f}
            merged_fields = list(existing_map.values())
            fields_file.write_text(
                json.dumps(merged_fields, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        else:
            merged_fields = self.load_fields(entity_code)

        # 如果对象已提交，检测字段变化并标记 dirty
        raw_ws = self._load_workspace_raw()
        obj_status = raw_ws.get("objects", {}).get(entity_code, {}).get("status", "draft")
        if obj_status == "submitted" and fields is not None:
            diff = self.diff_fields(entity_code, merged_fields)
            if diff.has_changes():
                self.update_entity_status(entity_code, "dirty")

        missing: list[str] = []
        if not definition.get("entity_name"):
            missing.append("entity_name")
        if not merged_fields:
            missing.append("fields")

        return {
            "ok": True,
            "state": {**definition, "fields": merged_fields},
            "missing": missing,
        }

    def _load_definition(self, entity_code: str) -> dict[str, Any] | None:
        def_file = self._root / "objects" / entity_code / "definition.json"
        if not def_file.exists():
            return None
        return json.loads(def_file.read_text(encoding="utf-8"))  # type: ignore[no-any-return]

    def save_submitted_field_snapshot(self, entity_code: str, fields: list[dict[str, Any]]) -> None:
        """将当前字段列表写入 definition.json 的 submitted_fields 快照（submit 成功后调用）。

        快照只保留 property_code 和 data_type，用于后续 diff 检测。
        """
        def_file = self._root / "objects" / entity_code / "definition.json"
        definition: dict[str, Any] = {"entity_code": entity_code}
        if def_file.exists():
            definition = json.loads(def_file.read_text(encoding="utf-8"))
        definition["submitted_fields"] = [
            {"property_code": f["property_code"], "data_type": f.get("data_type", "STRING")}
            for f in fields
            if f.get("property_code")
        ]
        def_file.write_text(json.dumps(definition, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_submitted_field_snapshot(self, entity_code: str) -> list[dict[str, Any]]:
        """读取上次提交时的字段快照（property_code + data_type 列表），不存在时返回空列表。"""
        defn = self._load_definition(entity_code)
        if defn is None:
            return []
        return cast("list[dict[str, Any]]", defn.get("submitted_fields", []))

    def diff_fields(self, entity_code: str, current_fields: list[dict[str, Any]]) -> FieldDiff:
        """对比 submitted_fields 快照与当前字段，返回 FieldDiff。

        Args:
            entity_code: 对象编码。
            current_fields: 当前 fields.json 内容。
        """
        snapshot = {
            f["property_code"]: f["data_type"]
            for f in self.get_submitted_field_snapshot(entity_code)
            if f.get("property_code")
        }
        if not snapshot:
            # 无快照（尚未提交过）：不产生 diff
            return FieldDiff()

        current_map = {
            f["property_code"]: f.get("data_type", "STRING")
            for f in current_fields
            if f.get("property_code")
        }

        added = [f for f in current_fields if f.get("property_code") not in snapshot]
        removed = [code for code in snapshot if code not in current_map]
        type_changed = [
            (code, snapshot[code], current_map[code])
            for code in snapshot
            if code in current_map and snapshot[code] != current_map[code]
        ]
        return FieldDiff(added=added, removed=removed, type_changed=type_changed)

    def load_fields(self, entity_code: str) -> list[dict[str, Any]]:
        fields_file = self._root / "objects" / entity_code / "fields.json"
        if not fields_file.exists():
            return []
        return json.loads(fields_file.read_text(encoding="utf-8"))  # type: ignore[no-any-return]

    def get_object_full(self, entity_code: str) -> dict[str, Any] | None:
        """返回对象完整定义（definition + fields + action列表）。"""
        defn = self._load_definition(entity_code)
        if defn is None:
            return None
        fields = self.load_fields(entity_code)
        action_codes = self._list_action_codes(entity_code)
        actions = []
        for ac in action_codes:
            full = self.get_action_full(entity_code, ac)
            if full:
                action_entry: dict[str, Any] = {
                    "action_code": ac,
                    "action_name": full.get("action_name", ""),
                    "action_desc": full.get("action_desc", ""),
                    "action_type": full.get("action_type", "OPERATION"),
                    "script": full.get("script", ""),
                    "params": full.get("params", []),
                }
                if full.get("object_references"):
                    action_entry["object_references"] = full["object_references"]
                actions.append(action_entry)
        return {**defn, "fields": fields, "actions": actions}

    def _list_entity_codes(self) -> list[str]:
        objects_dir = self._root / "objects"
        if not objects_dir.exists():
            return []
        return sorted(p.name for p in objects_dir.iterdir() if p.is_dir())

    # ── action files ──────────────────────────────────────────────────────────

    def save_action(
        self,
        entity_code: str,
        action_code: str,
        action_name: str,
        script: str,
        params: list[dict[str, Any]],
        action_desc: str = "",
        action_type: str = "OPERATION",
        permission_roles: list[str] | None = None,
        object_references: list[str] | None = None,
    ) -> str:
        """写入 Action 脚本和元数据，返回相对路径。

        Args:
            action_type: "QUERY"（查询类，只读）或 "OPERATION"（操作类，写入/修改数据）
            object_references: 脚本依赖的其他对象编码列表，用于执行时按需注入 mapper
        """
        actions_dir = self._root / "objects" / entity_code / "actions"
        actions_dir.mkdir(parents=True, exist_ok=True)

        (actions_dir / f"{action_code}.py").write_text(script, encoding="utf-8")

        # action_type 规范化：只接受 QUERY / OPERATION
        normalized_type = action_type.upper() if action_type else "OPERATION"
        if normalized_type not in ("QUERY", "OPERATION"):
            normalized_type = "OPERATION"

        meta: dict[str, Any] = {
            "action_code": action_code,
            "action_name": action_name,
            "action_type": normalized_type,
        }
        if action_desc:
            meta["action_desc"] = action_desc
        if permission_roles:
            meta["permission_roles"] = permission_roles
        if params:
            meta["params"] = params
        if object_references:
            meta["object_references"] = object_references
        (actions_dir / f"{action_code}.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # Action 变更后，若对象已提交则标记 dirty（触发下次 batch_submit 重新生成 OWL）
        raw_ws = self._load_workspace_raw()
        obj_status = raw_ws.get("objects", {}).get(entity_code, {}).get("status", "draft")
        if obj_status == "submitted":
            self.update_entity_status(entity_code, "dirty")

        return f"objects/{entity_code}/actions/{action_code}.py"

    def load_action_script(self, entity_code: str, action_code: str) -> str | None:
        script_file = self._root / "objects" / entity_code / "actions" / f"{action_code}.py"
        if not script_file.exists():
            return None
        return script_file.read_text(encoding="utf-8")

    def load_action_meta(self, entity_code: str, action_code: str) -> dict[str, Any] | None:
        meta_file = self._root / "objects" / entity_code / "actions" / f"{action_code}.json"
        if not meta_file.exists():
            return None
        return json.loads(meta_file.read_text(encoding="utf-8"))  # type: ignore[no-any-return]

    def get_action_full(self, entity_code: str, action_code: str) -> dict[str, Any] | None:
        meta = self.load_action_meta(entity_code, action_code)
        if meta is None:
            return None
        script = self.load_action_script(entity_code, action_code) or ""
        return {**meta, "script": script}

    def _list_action_codes(self, entity_code: str) -> list[str]:
        actions_dir = self._root / "objects" / entity_code / "actions"
        if not actions_dir.exists():
            return []
        return sorted(p.stem for p in actions_dir.glob("*.json"))

    def list_actions_summary(self, entity_code: str) -> list[dict[str, Any]]:
        result = []
        for ac in self._list_action_codes(entity_code):
            meta = self.load_action_meta(entity_code, ac) or {}
            result.append(
                {
                    "action_code": ac,
                    "action_name": meta.get("action_name", ""),
                    "action_desc": meta.get("action_desc", ""),
                    "action_type": meta.get("action_type", "OPERATION"),
                    "param_count": len(meta.get("params", [])),
                }
            )
        return result

    # ── view files ────────────────────────────────────────────────────────────

    def save_view(
        self,
        view_code: str,
        view_name: str = "",
        view_desc: str = "",
        object_codes: list[str] | None = None,
        object_relations: list[dict[str, Any]] | None = None,
        fields: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """合并写入视图定义，返回带 missing 的结果。"""
        views_dir = self._root / "views"
        views_dir.mkdir(exist_ok=True)

        view_file = views_dir / f"{view_code}.json"
        state: dict[str, Any] = {"view_code": view_code}
        if view_file.exists():
            state = json.loads(view_file.read_text(encoding="utf-8"))

        if view_name:
            state["view_name"] = view_name
        if view_desc:
            state["view_desc"] = view_desc
        if object_codes:
            state["object_codes"] = object_codes

        if object_relations:
            existing_rels: dict[tuple[str, str, str, str], dict[str, Any]] = {
                (
                    r.get("source_object_code", ""),
                    r.get("source_object_field_code", ""),
                    r.get("target_object_code", ""),
                    r.get("target_object_field_code", ""),
                ): r
                for r in state.get("object_relations", [])
            }
            for rel in object_relations:
                key: tuple[str, str, str, str] = (
                    rel.get("source_object_code", ""),
                    rel.get("source_object_field_code", ""),
                    rel.get("target_object_code", ""),
                    rel.get("target_object_field_code", ""),
                )
                existing_rels[key] = {**existing_rels.get(key, {}), **rel}
            state["object_relations"] = list(existing_rels.values())

        # Auto-derive fields from objects when first collecting
        if fields is None and object_codes and not state.get("fields"):
            derived = self._derive_view_fields(object_codes)
            if derived:
                state["fields"] = derived
        elif fields is not None:
            existing_fmap: dict[str, dict[str, Any]] = {
                f["property_code"]: f for f in state.get("fields", [])
            }
            for f in fields:
                code = f.get("property_code", "")
                if code:
                    existing_fmap[code] = {**existing_fmap.get(code, {}), **f}
            state["fields"] = list(existing_fmap.values())

        view_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

        missing: list[str] = []
        if not state.get("view_name"):
            missing.append("view_name")
        if not state.get("object_codes"):
            missing.append("object_codes")
        if not state.get("object_relations"):
            missing.append("object_relations")

        return {
            "ok": True,
            "view_code": view_code,
            "fields_count": len(state.get("fields", [])),
            "missing": missing,
        }

    def _derive_view_fields(self, object_codes: list[str]) -> list[dict[str, Any]]:
        """从各对象字段自动推导视图字段列表。"""
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for obj_code in object_codes:
            for f in self.load_fields(obj_code):
                code = f.get("property_code", "")
                if code and code not in seen:
                    seen.add(code)
                    result.append(
                        {
                            "property_code": code,
                            "property_name": f.get("property_name", code),
                            "data_type": f.get("data_type", "STRING"),
                            "ext_property": f.get("ext_property", {}),
                            "_source_object_code": obj_code,
                        }
                    )
        return result

    def _load_view_def(self, view_code: str) -> dict[str, Any] | None:
        view_file = self._root / "views" / f"{view_code}.json"
        if not view_file.exists():
            return None
        return json.loads(view_file.read_text(encoding="utf-8"))  # type: ignore[no-any-return]

    def _list_view_codes(self) -> list[str]:
        views_dir = self._root / "views"
        if not views_dir.exists():
            return []
        return sorted(p.stem for p in views_dir.glob("*.json"))

    def get_view_full(self, view_code: str) -> dict[str, Any] | None:
        return self._load_view_def(view_code)

    def list_views_summary(self) -> list[dict[str, Any]]:
        result = []
        for vc in self._list_view_codes():
            vdef = self._load_view_def(vc) or {}
            result.append(
                {
                    "view_code": vc,
                    "view_name": vdef.get("view_name", ""),
                    "view_desc": vdef.get("view_desc", ""),
                    "object_count": len(vdef.get("object_codes", [])),
                    "field_count": len(vdef.get("fields", [])),
                }
            )
        return result

    # ── SDK files ─────────────────────────────────────────────────────────────

    def save_sdk(self, entity_code: str, content: str) -> None:
        sdk_dir = self._root / "sdk"
        sdk_dir.mkdir(exist_ok=True)
        (sdk_dir / f"{entity_code}_sdk.py").write_text(content, encoding="utf-8")

    def load_sdk(self, entity_code: str) -> str | None:
        sdk_file = self._root / "sdk" / f"{entity_code}_sdk.py"
        if not sdk_file.exists():
            return None
        return sdk_file.read_text(encoding="utf-8")

    # ── list helpers ──────────────────────────────────────────────────────────

    def list_objects_summary(self) -> list[dict[str, Any]]:
        raw = self._load_workspace_raw()
        status_map: dict[str, Any] = raw.get("objects", {})
        result = []
        for entity_code in self._list_entity_codes():
            defn = self._load_definition(entity_code) or {}
            st = status_map.get(entity_code, {})
            result.append(
                {
                    "entity_code": entity_code,
                    "entity_name": defn.get("entity_name", ""),
                    "status": st.get("status", "draft"),
                    "resource_id": st.get("resource_id", ""),
                    "action_count": len(self._list_action_codes(entity_code)),
                    "field_count": len(self.load_fields(entity_code)),
                }
            )
        return result

    # ── delete helpers ────────────────────────────────────────────────────────

    def delete_action(self, entity_code: str, action_code: str) -> bool:
        """删除 Action 文件（.py + .json），返回是否实际删除了文件。"""
        actions_dir = self._root / "objects" / entity_code / "actions"
        deleted = False
        for ext in (".py", ".json"):
            f = actions_dir / f"{action_code}{ext}"
            if f.exists():
                f.unlink()
                deleted = True

        # Action 删除后，若对象已提交则标记 dirty（触发下次 batch_submit 重新生成 OWL）
        if deleted:
            raw_ws = self._load_workspace_raw()
            obj_status = raw_ws.get("objects", {}).get(entity_code, {}).get("status", "draft")
            if obj_status == "submitted":
                self.update_entity_status(entity_code, "dirty")

        return deleted

    def delete_object(self, entity_code: str) -> bool:
        """删除对象目录（含 definition.json / fields.json / actions/ / sdk/），返回是否存在。"""
        import shutil

        obj_dir = self._root / "objects" / entity_code
        sdk_file = self._root / "sdk" / f"{entity_code}_sdk.py"
        existed = obj_dir.exists()
        if obj_dir.exists():
            shutil.rmtree(obj_dir)
        if sdk_file.exists():
            sdk_file.unlink()
        # 从 workspace.json 中移除该对象的状态记录
        ws_file = self._root / "workspace.json"
        if ws_file.exists():
            try:
                raw = json.loads(ws_file.read_text(encoding="utf-8"))
                raw.setdefault("objects", {}).pop(entity_code, None)
                ws_file.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                logger.warning("删除对象 %s 时 workspace.json 清理失败", entity_code)
        return existed

    def delete_view(self, view_code: str) -> bool:
        """删除视图文件，返回是否存在。"""
        view_file = self._root / "views" / f"{view_code}.json"
        existed = view_file.exists()
        if existed:
            view_file.unlink()
        # 从 workspace.json 中移除该视图的状态记录
        ws_file = self._root / "workspace.json"
        if ws_file.exists():
            try:
                raw = json.loads(ws_file.read_text(encoding="utf-8"))
                raw.setdefault("views", {}).pop(view_code, None)
                ws_file.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                logger.warning("删除视图 %s 时 workspace.json 清理失败", view_code)
        return existed

    def delete_workspace(self) -> bool:
        """删除整个工作区目录，返回是否存在。"""
        import shutil

        existed = self._root.exists()
        if existed:
            shutil.rmtree(self._root)
        return existed


# ── 模块级辅助函数 ─────────────────────────────────────────────────────────────


def list_user_workspaces(user_code: str) -> list[dict[str, Any]]:
    """列出指定用户的所有工作区及待提交摘要。

    Args:
        user_code: 用户标识，对应工作区目录层级。

    Returns:
        工作区列表，每项包含：
        - workspace_name: 工作区名称
        - workspace_desc: 工作区描述
        - object_count: 对象总数
        - view_count: 视图总数
        - pending_count: 未提交条目数（status 为 draft 或 failed 的对象 + 视图）
        - has_pending: 是否存在未提交条目
    """
    storage_root = _storage_root()
    user_root = storage_root / user_code
    logger.debug("list_user_workspaces: storage_root=%s user_root=%s", storage_root, user_root)

    if not user_root.exists():
        logger.info("用户工作区根目录不存在，返回空列表: %s", user_root)
        return []

    result: list[dict[str, Any]] = []
    try:
        entries = sorted(user_root.iterdir())
    except OSError as exc:
        raise OSError(f"无法读取用户工作区目录 {user_root}: {exc}") from exc

    for ws_dir in entries:
        if not ws_dir.is_dir():
            continue
        ws_file = ws_dir / "workspace.json"
        if not ws_file.exists():
            continue
        try:
            raw: dict[str, Any] = json.loads(ws_file.read_text(encoding="utf-8"))
        except OSError as exc:
            logger.warning("读取工作区文件失败 %s: %s", ws_file, exc)
            continue
        except json.JSONDecodeError as exc:
            logger.warning("工作区文件 JSON 解析失败 %s: %s", ws_file, exc)
            continue

        objects_status: dict[str, Any] = raw.get("objects", {})
        views_status: dict[str, Any] = raw.get("views", {})

        # 统计文件系统中实际存在的对象和视图数
        objects_dir = ws_dir / "objects"
        actual_object_codes = (
            sorted(p.name for p in objects_dir.iterdir() if p.is_dir())
            if objects_dir.exists()
            else []
        )
        views_dir = ws_dir / "views"
        actual_view_codes = (
            sorted(p.stem for p in views_dir.glob("*.json")) if views_dir.exists() else []
        )

        # 未提交：文件存在但 status 不是 submitted（draft / failed / dirty 均算 pending）
        pending_objects = [
            c
            for c in actual_object_codes
            if objects_status.get(c, {}).get("status", "draft") != "submitted"
        ]
        pending_views = [
            c
            for c in actual_view_codes
            if views_status.get(c, {}).get("status", "draft") != "submitted"
        ]
        pending_count = len(pending_objects) + len(pending_views)

        result.append(
            {
                "workspace_name": raw.get("workspace_name", ws_dir.name),
                "workspace_desc": raw.get("workspace_desc", ""),
                "object_count": len(actual_object_codes),
                "view_count": len(actual_view_codes),
                "pending_count": pending_count,
                "has_pending": pending_count > 0,
                "pending_objects": pending_objects,
                "pending_views": pending_views,
            }
        )

    return result
