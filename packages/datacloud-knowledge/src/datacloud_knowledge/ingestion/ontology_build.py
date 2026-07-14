"""对话式个人本体管理 — 业务编排层。

暴露 OntologyBuildSession，支持多轮信息收集与校验。
提交/删除/术语查询等编排逻辑已上移至 datacloud-platform 的 OntologyBuildMixin。
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Protocol

from datacloud_knowledge.ingestion.workspace_store import get_workspace_store

logger = logging.getLogger(__name__)

_VALID_DATA_TYPES = {"STRING", "INTEGER", "FLOAT", "BOOLEAN", "DATE"}
_VALID_PROPERTY_ROLES = {"DIMENSION", "MEASURE"}


class _ObjectFieldsStore(Protocol):
    def save(self, key: str, state: dict[str, Any], ttl: int = 3600) -> None: ...

    def load(self, key: str) -> dict[str, Any]: ...


# ── 字段格式校验（collect 阶段即时拒绝）──────────────────────────────────────


def _validate_fields_format(fields: list[dict[str, Any]]) -> list[str]:
    """返回格式错误描述列表，空列表表示全部合法。"""
    errors: list[str] = []
    seen_codes: set[str] = set()
    for f in fields:
        code = f.get("property_code", "")
        if not code:
            errors.append("field 缺少 property_code")
            continue
        if code in seen_codes:
            errors.append(f"property_code 重复: {code}")
        seen_codes.add(code)
        dt = f.get("data_type", "")
        if dt and dt not in _VALID_DATA_TYPES:
            errors.append(f"非法 data_type: {dt}，合法值: {sorted(_VALID_DATA_TYPES)}")
        role_rule = (f.get("ext_property") or {}).get("property_role_rule", {})
        role = role_rule.get("property_role", "")
        if role and role not in _VALID_PROPERTY_ROLES:
            errors.append(f"非法 property_role: {role}")
        if f.get("term_type_code") and f.get("term_values"):
            errors.append(f"term_type_code 与 term_values 互斥，property_code={code}")
    return errors


# ── OntologyBuildSession ──────────────────────────────────────────────────────

_OBJ_FIELDS_CACHE_TTL = 86400 * 30  # 30 天


def _obj_fields_cache_key(prefix: str, object_code: str) -> str:
    return f"{prefix}_obj_fields_{object_code}"


def _cache_obj_fields(
    store: _ObjectFieldsStore, prefix: str, object_code: str, fields: list[dict[str, Any]]
) -> None:
    """缓存对象字段定义，供视图收集时自动展开。"""
    store.save(
        _obj_fields_cache_key(prefix, object_code), {"fields": fields}, ttl=_OBJ_FIELDS_CACHE_TTL
    )


def _load_obj_fields_from_cache(
    store: _ObjectFieldsStore, prefix: str, object_codes: list[str]
) -> list[dict[str, Any]]:
    """从缓存中加载指定对象的所有字段定义，去重并标注来源对象。"""
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for obj_code in object_codes:
        cached = store.load(_obj_fields_cache_key(prefix, obj_code))
        for f in cached.get("fields", []):
            code = f.get("property_code", "")
            if not code:
                continue
            if code in seen:
                continue
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


class OntologyBuildSession:
    """以 session_id + entity_code / view_code 为唯一键，管理本体构建的暂存状态。

    暂存存储：WorkspaceStore 抽象（Redis / 本地文件），通过 ONTOLOGY_STORE 环境变量切换。
    key 规则：{session_id}_{entity_code}（session_id 为空时退化为 {entity_code}）。
    """

    def __init__(self, *, user_code: str = "") -> None:
        """初始化 Session。

        Args:
            user_code: 用户标识，用于 workspace key 前缀和实体唯一编码生成。
                       由调用方（OntologyBuildMixin）从请求上下文注入。
        """
        self._user_code = user_code

    # ── 信息收集 ──────────────────────────────────────────────────────────────

    def collect_object_info(
        self,
        entity_code: str,
        session_id: str = "",
        entity_name: str = "",
        entity_desc: str = "",
        fields: list[dict[str, Any]] | None = None,
        kb_id: str = "",
        kb_directory: str = "",
        base_id: str = "",
        ext_property: dict = "",
    ) -> dict[str, Any]:
        """收集本体对象信息，合并到暂存状态，返回当前完整状态。

        多轮对话反复调用，每次只需传入本轮新增/修改的字段，未传入的字段保留上次的值。
        entity_code 会自动拼上工号和随机后缀，保证全局唯一。
        """
        if fields:
            fmt_errors = _validate_fields_format(fields)
            if fmt_errors:
                return {"ok": False, "errors": fmt_errors}

        user_code = self._user_code

        store = get_workspace_store()
        # key 加工号前缀，隔离多用户并发
        prefix = f"{user_code}:" if user_code else ""
        key = f"{prefix}{session_id}_{entity_code}" if session_id else f"{prefix}{entity_code}"
        original_key = key
        state: dict[str, Any] = store.load(key)

        # 首次收集时，自动生成带工号+随机后缀的唯一编码
        if not state.get("entity_code"):
            short_id = uuid.uuid4().hex[:6]
            unique_code = (
                f"p_{entity_code}_{user_code}_{short_id}"
                if user_code
                else f"p_{entity_code}_{short_id}"
            )
            state["entity_code"] = unique_code
            key = f"{prefix}{session_id}_{unique_code}" if session_id else f"{prefix}{unique_code}"
        else:
            # 用 state 中的 entity_code 构造保存 key（可能是生成的唯一码）
            stored_code = state["entity_code"]
            key = f"{prefix}{session_id}_{stored_code}" if session_id else f"{prefix}{stored_code}"
        if entity_name:
            state["entity_name"] = entity_name
        if entity_desc:
            state["entity_desc"] = entity_desc
        if kb_id:
            state["kb_id"] = kb_id
            # 补充提示描述，让模型理解需通过 query 参数传入完整文件路径和内容
            _supplement = "进行创建写入和查询详情分析时，需通过 query 参数传入完整的文件路径和完整的文件内容，以确保能获取到完整的数据上下文。"
            if state.get("entity_desc"):
                state["entity_desc"] = state["entity_desc"] + "；" + _supplement
            else:
                state["entity_desc"] = _supplement
        if kb_directory:
            state["kb_directory"] = kb_directory
        if base_id:
            state["base_id"] = base_id
        if ext_property:
            state["ext_property"] = ext_property

        if fields:
            existing: dict[str, dict[str, Any]] = {
                f["property_code"]: f for f in state.get("fields", [])
            }
            for field in fields:
                existing[field["property_code"]] = {
                    **existing.get(field["property_code"], {}),
                    **field,
                }
            state["fields"] = list(existing.values())

        store.save(key, state, ttl=3600)
        # 同时用原始短码 key 保存，让 submit 传短码也能查找到
        if original_key != key:
            store.save(original_key, state, ttl=3600)

        missing: list[str] = []
        if not state.get("entity_name"):
            missing.append("entity_name")
        if not state.get("fields"):
            missing.append("fields")

        return {**state, "missing": missing}

    def collect_view_info(
        self,
        view_code: str,
        session_id: str = "",
        view_name: str = "",
        view_desc: str = "",
        object_codes: list[str] | None = None,
        object_relations: list[dict[str, Any]] | None = None,
        fields: list[dict[str, Any]] | None = None,
        base_id: str = "",
    ) -> dict[str, Any]:
        """收集本体视图信息，合并到暂存状态，返回当前完整状态。

        view_code 会自动拼上工号和随机后缀，保证全局唯一。
        object_codes 传入后自动从对象字段缓存加载字段定义；
        fields 可用于追加计算属性或覆盖自动加载的字段（按 property_code 合并，
        传入的同名覆盖，不重复的自动保留）。
        """
        user_code = self._user_code

        store = get_workspace_store()
        prefix = f"{user_code}:" if user_code else ""
        key = f"{prefix}{session_id}_{view_code}" if session_id else f"{prefix}{view_code}"
        state: dict[str, Any] = store.load(key)

        # 首次收集时，自动生成带工号+随机后缀的唯一编码
        if not state.get("view_code"):
            short_id = uuid.uuid4().hex[:6]
            unique_code = (
                f"pv_{view_code}_{user_code}_{short_id}"
                if user_code
                else f"pv_{view_code}_{short_id}"
            )
            state["view_code"] = unique_code
        if view_name:
            state["view_name"] = view_name
        if view_desc:
            state["view_desc"] = view_desc
        if object_codes:
            state["object_codes"] = object_codes
            # 从对象字段缓存自动加载（首次 collect 时）
            if not state.get("fields"):
                auto_fields = _load_obj_fields_from_cache(store, prefix, object_codes)
                if auto_fields:
                    state["fields"] = auto_fields

        if object_relations:

            def _rel_key(r: dict[str, Any]) -> tuple[str, str, str, str]:
                return (
                    r.get("source_object_code", ""),
                    r.get("source_object_field_code", ""),
                    r.get("target_object_code", ""),
                    r.get("target_object_field_code", ""),
                )

            existing_rels: dict[tuple[str, str, str, str], dict[str, Any]] = {
                _rel_key(r): r for r in state.get("object_relations", [])
            }
            for rel in object_relations:
                existing_rels[_rel_key(rel)] = {**existing_rels.get(_rel_key(rel), {}), **rel}
            state["object_relations"] = list(existing_rels.values())

        # 用户传入的 fields 覆盖/追加（同名覆盖，新字段追加）
        if fields:
            existing: dict[str, dict[str, Any]] = {
                f["property_code"]: f for f in state.get("fields", [])
            }
            for field in fields:
                existing[field["property_code"]] = {
                    **existing.get(field["property_code"], {}),
                    **field,
                }
            state["fields"] = list(existing.values())

        if base_id:
            state["base_id"] = base_id

        store.save(key, state, ttl=3600)

        missing: list[str] = []
        if not state.get("view_name"):
            missing.append("view_name")
        if not state.get("object_relations"):
            missing.append("object_relations")
        if not state.get("object_codes"):
            missing.append("object_codes")

        return {**state, "missing": missing}
