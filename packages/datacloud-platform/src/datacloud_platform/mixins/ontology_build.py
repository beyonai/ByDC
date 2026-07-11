"""OntologyBuildMixin — 个人本体构建编排层。

将 OntologyBuildSession 的多轮信息收集能力与 DatacloudPlatform 的 CRUD 能力组合，
形成完整的「收集 → 校验 → 提交 → 删除」构建流水线。
"""

from __future__ import annotations

import logging
import os
from typing import Any, cast

from datacloud_platform.backends._contracts import _HasTermBackend
from datacloud_platform.models.object_type import ObjectType
from datacloud_platform.models.property import Property
from datacloud_platform.models.relation import Relation
from datacloud_platform.models.view import View, ViewProperty

logger = logging.getLogger(__name__)


def _extract_search_items(result: Any) -> list[Any]:
    """从 search_terms 响应中提取 items 列表，兼容 dict 和对象。"""
    if isinstance(result, dict):
        return result.get("items", [])  # type: ignore[no-any-return]
    return getattr(result, "items", [])


def _get_attr(obj: Any, name: str) -> str:
    """从 dict 或对象中获取属性值，始终返回字符串。"""
    if isinstance(obj, dict):
        return str(obj.get(name, ""))
    return str(getattr(obj, name, ""))


class OntologyBuildMixin:
    """个人本体构建编排层。

    组合 OntologyBuildSession（workspace 暂存）与 DatacloudPlatform CRUD 能力。
    所有方法通过 self._ontology_for / self._term_for / self._default_base_id 访问
    平台能力，这些由 DatacloudPlatform 在组合时提供。
    """

    # ── Session 工厂 ────────────────────────────────────────────────────────

    @staticmethod
    def _build_session(user_code: str = "") -> Any:
        """每次调用返回新的 OntologyBuildSession，避免跨 event loop 复用 asyncio 对象。"""
        from datacloud_knowledge.ingestion.ontology_build import OntologyBuildSession

        return OntologyBuildSession(user_code=user_code)

    # ── 信息收集（委托给 OntologyBuildSession）─────────────────────────────────

    def collect_object_info(
        self,
        *,
        user_code: str = "",
        entity_code: str,
        session_id: str = "",
        entity_name: str = "",
        entity_desc: str = "",
        fields: list[dict[str, Any]] | None = None,
        kb_id: str = "",
        kb_directory: str = "",
        base_id: str = "",
    ) -> dict[str, Any]:
        """收集本体对象信息（多轮），委托给 OntologyBuildSession。"""
        session = self._build_session(user_code)
        return cast(
            dict[str, Any],
            session.collect_object_info(
                entity_code=entity_code,
                session_id=session_id,
                entity_name=entity_name,
                entity_desc=entity_desc,
                fields=fields,
                kb_id=kb_id,
                kb_directory=kb_directory,
                base_id=base_id,
            ),
        )

    def collect_view_info(
        self,
        *,
        user_code: str = "",
        view_code: str,
        session_id: str = "",
        view_name: str = "",
        view_desc: str = "",
        object_codes: list[str] | None = None,
        object_relations: list[dict[str, Any]] | None = None,
        fields: list[dict[str, Any]] | None = None,
        base_id: str = "",
    ) -> dict[str, Any]:
        """收集本体视图信息（多轮），委托给 OntologyBuildSession。"""
        session = self._build_session(user_code)
        return cast(
            dict[str, Any],
            session.collect_view_info(
                view_code=view_code,
                session_id=session_id,
                view_name=view_name,
                view_desc=view_desc,
                object_codes=object_codes,
                object_relations=object_relations,
                fields=fields,
                base_id=base_id,
            ),
        )

    # ── 信息提交（workspace state → CRUD）──────────────────────────────────────

    def submit_object(
        self,
        *,
        user_code: str = "",
        entity_code: str,
        session_id: str = "",
        base_id: str = "",
        scene_id: str = "",
    ) -> dict[str, Any]:
        """提交本体对象：加载 workspace state → 构建 ObjectType → 走 CRUD 创建。

        Args:
            user_code: 用户标识。
            entity_code: 原始实体编码（用户输入的）。
            session_id: 多轮会话 ID。
            base_id: 目标本体库 ID，空则取第一个注册的 base。
            scene_id: 目标场景 ID，空则使用默认场景。
        """
        from datacloud_knowledge.ingestion.ontology_build import _cache_obj_fields
        from datacloud_knowledge.ingestion.workspace_store import get_workspace_store

        # 1. 加载 workspace state
        session = self._build_session(user_code)
        state = session.collect_object_info(
            entity_code=entity_code, session_id=session_id
        )
        if not state.get("entity_code"):
            return {"ok": False, "error": "暂存状态不存在，请先收集对象信息"}

        missing = state.get("missing", [])
        if missing:
            return {"ok": False, "missing": missing}

        actual_entity_code: str = state["entity_code"]
        entity_source = "KNOWLEDGE_BASE" if state.get("kb_id") else "DYNAMIC_TABLE"

        # 2. 解析 base_id / scene_id
        if not base_id:
            base_id = self._default_base_id()  # type: ignore[attr-defined]

        # 3. 构建 ObjectType
        source_config: dict[str, Any] | None = None
        table_name: str | None = None
        datasource_alias: str | None = None
        if entity_source == "KNOWLEDGE_BASE":
            source_config = {}
            if state.get("kb_id"):
                source_config["kb_id"] = state["kb_id"]
            if state.get("kb_directory"):
                source_config["kb_directory"] = state["kb_directory"]
        elif entity_source == "DYNAMIC_TABLE":
            # DYNAMIC_TABLE 的物理表名与 object_code 一致
            table_name = actual_entity_code
            from datacloud_platform.adapters.data_adapter._base import (  # noqa: PLC0415
                _DEFAULT_DYNAMIC_DATASOURCE_ALIAS,
            )

            datasource_alias = _DEFAULT_DYNAMIC_DATASOURCE_ALIAS
            # 含 alias 和 jdbc_url 让 _extract_datasource_configs_from_objects 能自动发现
            # 完整的 SQLite 数据源配置（包括 scoped loader 路径）
            mount = os.environ.get("FILE_STORAGE_MINIO_MOUNT_PATH", "")
            source_config: dict[str, Any] = {
                "db_type": "SQLITE",
                "alias": _DEFAULT_DYNAMIC_DATASOURCE_ALIAS,
            }
            if mount:
                source_config["jdbc_url"] = (
                    f"jdbc:sqlite:{mount}/byclaw-datacloud/personal_object.db"
                )

        obj = ObjectType(
            objectCode=actual_entity_code,
            objectName=state.get("entity_name", actual_entity_code),
            objectDesc=state.get("entity_desc", ""),
            objectSource=entity_source,
            baseId=base_id,
            ownerType="personal" if user_code else "enterprise",
            userCode=user_code or None,
            sourceConfig=source_config,
            tableName=table_name,
            datasourceAlias=datasource_alias,  # type: ignore[call-arg]
            properties=[
                Property(
                    propertyCode=f.get("property_code", ""),
                    propertyName=f.get("property_name", f.get("property_code", "")),
                    propertyDesc=f.get("property_desc", ""),
                    dataType=f.get("data_type", "STRING"),
                )
                for f in state.get("fields", [])
            ],
        )

        # 4. CRUD: 创建对象 + 加入场景
        self.create_object_with_scene(base_id, obj, scene_id)  # type: ignore[attr-defined]

        # 5. DYNAMIC_TABLE: 建物理表
        if entity_source == "DYNAMIC_TABLE":
            from datacloud_data_sdk.ddl.table_manager import create_table

            create_table(actual_entity_code, state.get("fields", []))

        # 6. 清理 workspace + 缓存对象字段
        store = get_workspace_store()
        prefix = f"{user_code}:" if user_code else ""
        key = (
            f"{prefix}{session_id}_{entity_code}"
            if session_id
            else f"{prefix}{entity_code}"
        )
        store.delete(key)
        _cache_obj_fields(store, prefix, actual_entity_code, state.get("fields", []))

        return {
            "ok": True,
            "entity_code": actual_entity_code,
            "entity_name": state.get("entity_name", ""),
            "entity_desc": state.get("entity_desc", ""),
            "original_code": entity_code,
            "message": (
                f"本体对象创建成功。"
                f"您输入的编码 '{entity_code}' 已自动分配为唯一编码 '{actual_entity_code}'"
            ),
        }

    def submit_view(
        self,
        *,
        user_code: str = "",
        view_code: str,
        session_id: str = "",
        base_id: str = "",
        scene_id: str = "",
    ) -> dict[str, Any]:
        """提交本体视图：加载 workspace state → 构建 View + Relation → 走 CRUD 创建。

        Args:
            user_code: 用户标识。
            view_code: 原始视图编码（用户输入的）。
            session_id: 多轮会话 ID。
            base_id: 目标本体库 ID，空则取第一个注册的 base。
            scene_id: 目标场景 ID，空则使用默认场景。
        """
        from datacloud_knowledge.ingestion.workspace_store import get_workspace_store

        # 1. 加载 workspace state
        session = self._build_session(user_code)
        state = session.collect_view_info(view_code=view_code, session_id=session_id)
        if not state.get("view_code"):
            return {"ok": False, "error": "暂存状态不存在，请先收集视图信息"}

        missing = state.get("missing", [])
        if missing:
            return {"ok": False, "missing": missing}

        actual_view_code: str = state["view_code"]
        object_codes: list[str] = state.get("object_codes", [])

        # 2. 解析 base_id / scene_id
        if not base_id:
            base_id = self._default_base_id()  # type: ignore[attr-defined]

        # 3. 构建 View
        view = View(
            viewCode=actual_view_code,
            viewName=state.get("view_name", actual_view_code),
            description=state.get("view_desc", ""),
            objectCodes=object_codes,
            ownerType="personal" if user_code else "enterprise",
            userCode=user_code or None,
            properties=[
                ViewProperty(
                    propertyCode=f.get("property_code", ""),
                    propertyName=f.get("property_name", f.get("property_code", "")),
                    sourceObject=f.get("_source_object_code", ""),
                    sourceObjectProperty=f.get("property_code", ""),
                )
                for f in state.get("fields", [])
            ],
        )

        # 4. CRUD: 创建视图 + 加入场景
        self.create_view_with_scene(base_id, view, scene_id)  # type: ignore[attr-defined]

        # 5. 创建对象间关系（MANY_TO_ONE）
        for rel in state.get("object_relations", []):
            relation = Relation(
                relationCode=f"{rel.get('source_object_code', '')}_to_{rel.get('target_object_code', '')}",
                relationName=rel.get("relation_name", ""),
                relationCardinality=rel.get("relation_type", "MANY_TO_ONE"),
                sourceObjectCode=rel.get("source_object_code", ""),
                targetObjectCode=rel.get("target_object_code", ""),
            )
            try:
                self.create_relation(base_id, relation)  # type: ignore[attr-defined]
            except Exception:
                logger.exception("创建视图关系失败: %s", rel)

        # 6. 清理 workspace
        store = get_workspace_store()
        prefix = f"{user_code}:" if user_code else ""
        key = (
            f"{prefix}{session_id}_{view_code}"
            if session_id
            else f"{prefix}{view_code}"
        )
        store.delete(key)

        return {
            "ok": True,
            "view_code": actual_view_code,
            "view_name": state.get("view_name", ""),
            "view_desc": state.get("view_desc", ""),
            "original_code": view_code,
            "message": (
                f"本体视图创建成功。"
                f"您输入的编码 '{view_code}' 已自动分配为唯一编码 '{actual_view_code}'"
            ),
        }

    # ── 删除 ────────────────────────────────────────────────────────────────

    def delete_build_object(
        self,
        *,
        user_code: str = "",
        entity_code: str,
        base_id: str = "",
    ) -> dict[str, Any]:
        """删除本体构建对象：删物理表 + 从所有场景移除并删除 ontology 元数据。

        Args:
            user_code: 用户标识。
            entity_code: 实体编码。
            base_id: 目标本体库 ID，空则取第一个注册的 base。
        """
        entity_code = entity_code.strip()
        if not entity_code:
            return {"ok": False, "error": "entity_code 不能为空"}

        if not base_id:
            base_id = self._default_base_id()  # type: ignore[attr-defined]

        # 1. 删物理表
        from datacloud_data_sdk.ddl.table_manager import drop_table

        drop_table(entity_code, user_code)

        # 2. 从所有场景移除并删除 ontology 元数据
        self.delete_object_from_all_scenes(base_id, entity_code)  # type: ignore[attr-defined]

        return {"ok": True, "entity_code": entity_code}

    def delete_build_view(
        self,
        *,
        user_code: str = "",
        view_code: str,
        base_id: str = "",
    ) -> dict[str, Any]:
        """删除本体视图：从所有场景移除并删除 ontology 元数据。

        Args:
            user_code: 用户标识。
            view_code: 视图编码。
            base_id: 目标本体库 ID，空则取第一个注册的 base。
        """
        view_code = view_code.strip()
        if not view_code:
            return {"ok": False, "error": "view_code 不能为空"}

        if not base_id:
            base_id = self._default_base_id()  # type: ignore[attr-defined]

        self.delete_view_from_all_scenes(base_id, view_code)  # type: ignore[attr-defined]

        return {"ok": True, "view_code": view_code}

    # ── 术语查询（走 TermBackend）─────────────────────────────────────────────

    def list_bindable_term_types(
        self: _HasTermBackend, *, base_id: str = "", keyword: str = ""
    ) -> list[dict[str, Any]]:
        """查询可绑定的 LIST_TERM / DICT_TERM 术语类型。

        兼容旧版 ontology-manager API，走 TermBackend：
        1. 通过 list_term_types 获取 category=1,2 的术语类型
        2. 对每个 type_code 取少量示例术语
        3. 按 type_code 分组返回 {type_code, samples}

        Args:
            base_id: 目标本体库 ID，空则取第一个注册的 base。
        """
        if not base_id:
            base_id = self._default_base_id()  # type: ignore[attr-defined]
        term = self._term_for(base_id)

        # 获取所有 LIST_TERM (category=1) 和 DICT_TERM (category=2) 类型
        list_types = term.list_term_types(type_category=1)
        dict_types = term.list_term_types(type_category=2)
        all_types = list_types + dict_types

        # keyword 过滤 type_code
        if keyword:
            kw = keyword.lower()
            all_types = [t for t in all_types if kw in t["type_code"].lower()]

        # 按 type_code 排序
        all_types.sort(key=lambda t: t["type_code"])

        # 每个类型取少量示例术语
        result: list[dict[str, Any]] = []
        for term_type in all_types:
            type_code: str = str(term_type["type_code"])
            search_result = term.search_terms(term_type=type_code, top_k=3)
            items = _extract_search_items(search_result)
            samples: list[dict[str, str]] = [
                {
                    "term_code": _get_attr(item, "term_code"),
                    "term_name": _get_attr(item, "term_name"),
                }
                for item in items
            ]
            result.append({"type_code": type_code, "samples": samples})

        return result

    def get_term_type_values(
        self: _HasTermBackend,
        *,
        term_type_code: str,
        base_id: str = "",
        keyword: str = "",
    ) -> list[dict[str, Any]]:
        """查询指定术语类型下的术语值。

        兼容旧版 ontology-manager API，走 TermBackend。

        Args:
            term_type_code: 术语类型编码。
            base_id: 目标本体库 ID，空则取第一个注册的 base。
        """
        if not base_id:
            base_id = self._default_base_id()  # type: ignore[attr-defined]
        term = self._term_for(base_id)

        search_result = term.search_terms(
            term_type=term_type_code,
            keyword=keyword or None,
            top_k=200,
        )
        items = _extract_search_items(search_result)
        return [
            {
                "term_code": _get_attr(item, "term_code"),
                "term_name": _get_attr(item, "term_name"),
            }
            for item in items
        ]
