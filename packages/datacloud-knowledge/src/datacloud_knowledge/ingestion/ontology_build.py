"""对话式个人本体管理 — 业务编排层。

暴露 OntologyBuildSession，支持多轮信息收集、校验、提交、删除。
"""

from __future__ import annotations

import logging
import os
import tempfile
import uuid
import zipfile
from pathlib import Path
from typing import Any

from datacloud_knowledge.adapters import create_reader
from datacloud_knowledge.ingestion.workspace_store import get_workspace_store
from datacloud_knowledge.provider import search_terms_by_type

logger = logging.getLogger(__name__)

_VALID_DATA_TYPES = {"STRING", "INTEGER", "FLOAT", "BOOLEAN", "DATE"}
_VALID_PROPERTY_ROLES = {"DIMENSION", "MEASURE"}


# ── 内部 HTTP 辅助（可被测试 mock）────────────────────────────────────────────


def _init_discovery_redis() -> None:
    """全局初始化服务发现所需的 Redis 连接（幂等，重复调用无副作用）。

    使用运行环境的标准 REDIS_* 环境变量，与 by-framework-docs 示例保持一致。
    """
    from by_framework.common.redis_client import init_redis  # type: ignore[import-untyped]

    init_redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        db=int(os.getenv("REDIS_DATABASE", "0")),
        password=os.getenv("REDIS_PASSWORD") or None,
        username=os.getenv("REDIS_USERNAME") or None,
    )


def _import_object_zip(zip_path: Path, token: str) -> dict[str, Any]:
    """通过服务发现调用门户服务 importObjectZip 上传 OWL zip。"""
    service_name = os.environ.get("BE_DOMAINNAME", "").strip()
    if not service_name:
        raise ValueError("BE_DOMAINNAME 环境变量未配置")

    async def _upload() -> dict[str, Any]:
        import httpx
        from by_framework.core.discovery import DiscoveryClient  # type: ignore[import-untyped]

        _init_discovery_redis()
        discovery_client = DiscoveryClient(cache_interval=5)
        try:
            instance = await discovery_client.discover(service_name, health_threshold_ms=-1)
            if not instance:
                return {"ok": False, "error": f"未找到服务实例: {service_name}"}

            base_url = f"http://{instance.host}:{instance.port}"
            async with httpx.AsyncClient(base_url=base_url, timeout=60.0) as client:
                with zip_path.open("rb") as f:
                    response = await client.post(
                        "/tool/importObjectZip",
                        headers={"Beyond-Token": token},
                        files={"file": (zip_path.name, f, "application/zip")},
                        data={"catalogId": "0", "ownerType": "personal"},
                    )
        finally:
            await discovery_client.close()

        if response.status_code != 200:
            return {"ok": False, "error": f"HTTP {response.status_code}"}
        body: dict[str, Any] = response.json() if response.content else {}
        if body.get("code", 0) != 0:
            return {"ok": False, "error": body.get("msg", "上传失败")}
        return {"ok": True, **body.get("data", {})}

    return _run_async_in_thread(_upload())


def _import_view_zip(zip_path: Path, token: str) -> dict[str, Any]:
    """通过服务发现调用门户服务 importViewZip 上传 OWL zip。"""
    service_name = os.environ.get("BE_DOMAINNAME", "").strip()
    if not service_name:
        raise ValueError("BE_DOMAINNAME 环境变量未配置")

    async def _upload() -> dict[str, Any]:
        import httpx
        from by_framework.core.discovery import DiscoveryClient  # type: ignore[import-untyped]

        _init_discovery_redis()
        discovery_client = DiscoveryClient(cache_interval=5)
        try:
            instance = await discovery_client.discover(service_name, health_threshold_ms=-1)
            if not instance:
                return {"ok": False, "error": f"未找到服务实例: {service_name}"}

            base_url = f"http://{instance.host}:{instance.port}"
            async with httpx.AsyncClient(base_url=base_url, timeout=60.0) as client:
                with zip_path.open("rb") as f:
                    response = await client.post(
                        "/tool/importViewZip",
                        headers={"Beyond-Token": token},
                        files={"file": (zip_path.name, f, "application/zip")},
                        data={"catalogId": "0", "ownerType": "personal"},
                    )
        finally:
            await discovery_client.close()

        if response.status_code != 200:
            return {"ok": False, "error": f"HTTP {response.status_code}"}
        body: dict[str, Any] = response.json() if response.content else {}
        if body.get("code", 0) != 0:
            return {"ok": False, "error": body.get("msg", "上传失败")}
        return {"ok": True, **body.get("data", {})}

    return _run_async_in_thread(_upload())


def _create_sqlite_table(entity_code: str, fields: list[dict[str, Any]], user_code: str) -> None:
    """通过 datacloud-data SDK 调用 SQLite HTTP API 建表。"""
    from datacloud_data_sdk.ddl.table_manager import create_table  # type: ignore[import-untyped]

    create_table(entity_code, fields, user_code)


def _run_async_in_thread(coro: Any) -> Any:
    import asyncio
    import threading

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:
            error["exc"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    if "exc" in error:
        raise error["exc"]
    return result.get("value")


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


class OntologyBuildSession:
    """以 session_id + entity_code / view_code 为唯一键，管理本体构建的暂存状态。

    暂存存储：WorkspaceStore 抽象（Redis / 本地文件），通过 ONTOLOGY_STORE 环境变量切换。
    key 规则：{session_id}_{entity_code}（session_id 为空时退化为 {entity_code}）。
    """

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
    ) -> dict[str, Any]:
        """收集本体对象信息，合并到暂存状态，返回当前完整状态。

        多轮对话反复调用，每次只需传入本轮新增/修改的字段，未传入的字段保留上次的值。
        entity_code 会自动拼上工号和随机后缀，保证全局唯一。
        """
        if fields:
            fmt_errors = _validate_fields_format(fields)
            if fmt_errors:
                return {"ok": False, "errors": fmt_errors}

        user_code = os.environ.get("USER_CODE", "")

        store = get_workspace_store()
        # key 加工号前缀，隔离多用户并发
        prefix = f"{user_code}:" if user_code else ""
        key = f"{prefix}{session_id}_{entity_code}" if session_id else f"{prefix}{entity_code}"
        state: dict[str, Any] = store.load(key)

        # 首次收集时，自动生成带工号+随机后缀的唯一编码
        if not state.get("entity_code"):
            short_id = uuid.uuid4().hex[:6]
            unique_code = f"p_{entity_code}_{user_code}_{short_id}" if user_code else f"p_{entity_code}_{short_id}"
            state["entity_code"] = unique_code
        if entity_name:
            state["entity_name"] = entity_name
        if entity_desc:
            state["entity_desc"] = entity_desc
        if kb_id:
            state["kb_id"] = kb_id
        if kb_directory:
            state["kb_directory"] = kb_directory

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
    ) -> dict[str, Any]:
        """收集本体视图信息，合并到暂存状态，返回当前完整状态。

        view_code 会自动拼上工号和随机后缀，保证全局唯一。
        """
        user_code = os.environ.get("USER_CODE", "")

        store = get_workspace_store()
        prefix = f"{user_code}:" if user_code else ""
        key = f"{prefix}{session_id}_{view_code}" if session_id else f"{prefix}{view_code}"
        state: dict[str, Any] = store.load(key)

        # 首次收集时，自动生成带工号+随机后缀的唯一编码
        if not state.get("view_code"):
            short_id = uuid.uuid4().hex[:6]
            unique_code = f"pv_{view_code}_{user_code}_{short_id}" if user_code else f"pv_{view_code}_{short_id}"
            state["view_code"] = unique_code
        if view_name:
            state["view_name"] = view_name
        if view_desc:
            state["view_desc"] = view_desc
        if object_codes:
            state["object_codes"] = object_codes

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

        store.save(key, state, ttl=3600)

        missing: list[str] = []
        if not state.get("view_name"):
            missing.append("view_name")
        if not state.get("object_relations"):
            missing.append("object_relations")

        return {**state, "missing": missing}

    # ── 术语查询 ──────────────────────────────────────────────────────────────

    def list_bindable_term_types(self, keyword: str = "") -> list[dict[str, Any]]:
        """查询可绑定的 LIST_TERM / DICT_TERM 术语类型（category=1 或 2）。"""
        reader = create_reader()
        type_codes = reader.get_type_codes_by_category(categories={1, 2})

        if keyword:
            type_codes = {tc for tc in type_codes if keyword.lower() in tc.lower()}

        result: list[dict[str, Any]] = []
        for type_code in sorted(type_codes):
            try:
                search_result = reader.search_terms(
                    term_type_code=type_code,
                    keyword=None,
                    limit=3,
                    offset=0,
                )
                samples = [
                    {"term_code": item.term_code, "term_name": item.term_name}
                    for item in (search_result.items if hasattr(search_result, "items") else [])
                ]
            except Exception:
                logger.exception("获取术语类型 %s 的示例值失败", type_code)
                samples = []
            result.append({"type_code": type_code, "samples": samples})

        return result

    def get_term_type_values(self, term_type_code: str, keyword: str = "") -> list[dict[str, Any]]:
        """查询指定术语类型下的所有术语值。"""
        search_result = search_terms_by_type(
            term_type_code=term_type_code,
            keyword=keyword or None,
            limit=200,
        )
        return [
            {"term_code": item.term_code, "term_name": item.term_name}
            for item in (search_result.items if hasattr(search_result, "items") else [])
        ]

    # ── 信息提交 ──────────────────────────────────────────────────────────────

    def submit_object(self, entity_code: str, session_id: str = "") -> dict[str, Any]:
        """提交本体对象：校验 → 生成 OWL → 建表（结构化）→ 上传 → 术语入库。"""

        user_code = os.environ.get("USER_CODE", "")
        store = get_workspace_store()
        prefix = f"{user_code}:" if user_code else ""
        key = f"{prefix}{session_id}_{entity_code}" if session_id else f"{prefix}{entity_code}"
        state = store.load(key)

        if not state:
            return {"ok": False, "error": "暂存状态不存在，请先收集对象信息"}

        missing: list[str] = []
        if not state.get("entity_name"):
            missing.append("entity_name")
        if not state.get("fields"):
            missing.append("fields")
        if missing:
            return {"ok": False, "missing": missing}

        state.setdefault("library_code", "PERSONAL_LIB")
        state.setdefault("domain_code", "PERSONAL_DOMAIN")
        state.setdefault("db_code", "personal_sqlite")
        state.setdefault("db_type", "PERSONAL_SQLITE")
        state["entity_source"] = "KNOWLEDGE_BASE" if state.get("kb_id") else "DYNAMIC_TABLE"

        token = os.environ.get("BEYOND_TOKEN", "")
        actual_entity_code = state["entity_code"]

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            generate_from_definition(state, output_dir)

            zip_path = output_dir / f"{actual_entity_code}.zip"
            _pack_zip(output_dir, zip_path)

            if state["entity_source"] == "DYNAMIC_TABLE":
                _create_sqlite_table(actual_entity_code, state.get("fields", []), user_code)

            upload_result = _import_object_zip(zip_path, token)
            if not upload_result.get("ok", True):
                return {"ok": False, "error": upload_result.get("error", "上传失败")}

        store.delete(key)
        resource_id = upload_result.get("resourceId") or upload_result.get("resource_id", "")
        return {"ok": True, "resource_id": resource_id}

    def submit_view(self, view_code: str, session_id: str = "") -> dict[str, Any]:
        """提交本体视图：校验 → 生成 OWL → 上传 → 术语入库。"""

        user_code = os.environ.get("USER_CODE", "")
        store = get_workspace_store()
        prefix = f"{user_code}:" if user_code else ""
        key = f"{prefix}{session_id}_{view_code}" if session_id else f"{prefix}{view_code}"
        state = store.load(key)

        if not state:
            return {"ok": False, "error": "暂存状态不存在，请先收集视图信息"}

        missing: list[str] = []
        if not state.get("view_name"):
            missing.append("view_name")
        if not state.get("object_relations"):
            missing.append("object_relations")
        if missing:
            return {"ok": False, "missing": missing}

        # 补齐 object_relations 缺失字段
        for rel in state.get("object_relations", []):
            rel.setdefault("relation_type", "MANY_TO_ONE")
            rel.setdefault("source_libeary", state.get("library_code", "PERSONAL_LIB"))
            rel.setdefault("target_libeary", state.get("library_code", "PERSONAL_LIB"))
            rel.setdefault("source_type", "EntityDefinition")
            rel.setdefault("target_type", "EntityDefinition")

        state.setdefault("library_code", "PERSONAL_LIB")
        state.setdefault("domain_code", "PERSONAL_DOMAIN")

        token = os.environ.get("BEYOND_TOKEN", "")
        actual_view_code = state["view_code"]

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            generate_from_definition(state, output_dir)

            zip_path = output_dir / f"{actual_view_code}.zip"
            _pack_zip(output_dir, zip_path)

            upload_result = _import_view_zip(zip_path, token)
            if not upload_result.get("ok", True):
                return {"ok": False, "error": upload_result.get("error", "上传失败")}

        store.delete(key)
        resource_id = upload_result.get("resourceId") or upload_result.get("resource_id", "")
        return {"ok": True, "resource_id": resource_id}

    # ── 删除 ──────────────────────────────────────────────────────────────────

    def delete_owl_scope(self, scope_type: str, resource_code: str) -> dict[str, Any]:
        """清除术语库中该 resource_code 下的所有术语数据。

        Args:
            scope_type: "OBJECT" 或 "VIEW"
            resource_code: 本体对象或视图的编码
        """
        reader = create_reader()
        scope = f"{scope_type.lower()}:{resource_code}"
        result: dict[str, Any] = reader.delete_scope(scope)
        if not result.get("ok"):
            raise RuntimeError(f"术语删除失败: {result.get('error')}")
        return {"ok": True}


# ── 工具函数 ──────────────────────────────────────────────────────────────────


def _pack_zip(source_dir: Path, zip_path: Path) -> None:
    """将 source_dir 下所有文件打包为 zip（不含 zip 文件本身）。"""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in source_dir.rglob("*"):
            if file == zip_path or not file.is_file():
                continue
            zf.write(file, file.relative_to(source_dir))


def _get_generate_from_definition() -> Any:
    """延迟导入 generate_from_definition，允许测试在模块级 patch。"""
    from datacloud_knowledge.ingestion.owl_generate import generator as _gen_mod

    return _gen_mod.generate_from_definition


def generate_from_definition(workspace_state: dict[str, Any], output_dir: Path) -> None:
    """模块级代理，供测试 patch 使用。实际实现在 owl_generate/generator.py。"""
    _get_generate_from_definition()(workspace_state, output_dir)
