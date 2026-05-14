"""知识包入库执行器：按 manifest 顺序在单个事务内写入数据库。

环境变量 DATACLOUD_KNOWLEDGE_IMPORT_BATCH_SIZE（默认 500，上限 10000）控制每个文件按批解析并入库的行数，减少与数据库的往返次数。

前提：调用方已通过 precheck.run() 校验，此处不再做格式校验。
字段映射（JSONL → DB）：
  domain_code   → domain.domain_id
  library_code  → term_library.library_id 与 term_library.library_code（同值）
  type_code     → term_type.type_code  （用 type_code 做 upsert key）
  term_code     → term.term_code
  term_name.name_id → 雪花 ID
  relation_code → term_relation.relation_id
  relation / term_name / term_knowledge 等外键列均存 term_id；JSONL 可同时提供
  term_id, 由 library_code+type_code+term_code 唯一决定

  雪花 ID：可选环境变量 DATACLOUD_KNOWLEDGE_SNOWFLAKE_DATACENTER_ID、
  DATACLOUD_KNOWLEDGE_SNOWFLAKE_WORKER_ID（各 0–31，默认 1）。

数据库访问已通过 BulkImportAdapter 解耦：本模块不再直接导入 psycopg，
连接、搜索路径、事务控制全部委托给适配器。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from datacloud_knowledge.adapters import create_bulk_importer

from . import owl_converter, owl_parser

logger = logging.getLogger(__name__)


# ── 批量处理器路由映射 ───────────────────────────────────────────────────────

# 方法名字符串，在 run() 中通过 getattr(adapter, name) 调用。
_STEP_BATCH_METHODS: dict[str, str] = {
    "meta_domain": "batch_process_domain",
    "meta_library": "batch_process_library",
    "term_type": "batch_process_term_type",
    "term": "batch_process_term",
    "relation": "batch_process_relation",
    "knowledge": "batch_process_knowledge",
}


def discover_owl_files(package_dir: Path) -> list[tuple[str, Path]]:
    """从目录结构自动发现 OWL 文件，返回按导入顺序排序的 (type, path) 列表。"""

    steps: list[tuple[str, Path]] = []
    term_types_files: list[Path] = []
    terms_files: list[Path] = []
    relations_files: list[Path] = []
    ontology_files: list[Path] = []

    for owl_file in sorted(package_dir.rglob("*.owl")):
        name = owl_file.name
        if name.endswith("_term_types.owl"):
            term_types_files.append(owl_file)
        elif name.endswith("_terms.owl"):
            terms_files.append(owl_file)
        elif name.endswith(
            (
                "_relations.owl",
                "_object_relations.owl",
                "_attribute_relations.owl",
                "_term_relations.owl",
            )
        ):
            relations_files.append(owl_file)
        else:
            ontology_files.append(owl_file)

    for owl_file in term_types_files:
        steps.append(("term_types", owl_file))
    for owl_file in terms_files:
        steps.append(("terms", owl_file))
    for owl_file in relations_files:
        steps.append(("relations", owl_file))
    for owl_file in ontology_files:
        steps.append(("ontology", owl_file))

    return steps


def _step_entity_type(step_type: str, filename: str) -> str:
    """与 precheck 保持相同推断逻辑。"""
    if step_type == "meta":
        return "meta_domain" if "domain" in filename else "meta_library"
    if step_type == "term_types":
        return "term_type"
    if step_type == "terms":
        return "term"
    if step_type == "relations":
        return "relation"
    return step_type


def _convert_owl_entities(
    step_type: str, rel_file: str, owl_entities: list[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    """将 OWL 解析结果转换为各批处理器可消费的数据结构。"""
    del step_type

    converted: dict[str, list[dict[str, Any]]] = {
        "meta_domain": [],
        "meta_library": [],
        "term_type": [],
        "term": [],
        "relation": [],
        "knowledge": [],
    }
    term_type_map: dict[str, dict[str, Any]] = {}
    type_category_map = {
        "LIST_TERM": "列表术语",
        "DICT_TERM": "字典术语",
        "ONTOLOGY_TERM": "本体术语",
        "DOC_NAME_TERM": "文档名称术语",
    }

    path_parts = Path(rel_file).parts
    scope_type = path_parts[0] if len(path_parts) >= 2 else ""
    scope_code = path_parts[1] if len(path_parts) >= 2 else ""
    scope_root_term_id: str | None = None

    for entity in owl_entities:
        if str(entity.get("entity_type", "")).strip() != "term":
            continue
        if str(entity.get("term_type_code") or "").strip() != scope_type:
            continue
        if str(entity.get("term_code") or "").strip() != scope_code:
            continue
        scope_root_term_id = str(entity.get("term_id") or "").strip() or None
        if scope_root_term_id:
            break

    for entity in owl_entities:
        entity_type = str(entity.get("entity_type", "")).strip()
        if not entity_type:
            continue

        if entity_type == "domain":
            converted["meta_domain"].append(owl_converter.convert_domain(entity))
            continue

        if entity_type == "library":
            library_code = owl_converter._pick_str(entity, "library_code")
            library_name = owl_converter._pick_str(entity, "library_name")
            if library_code:
                converted["meta_library"].append(
                    {
                        "library_code": library_code,
                        "library_name": library_name,
                    }
                )
            continue

        if entity_type == "term_type":
            term_type_obj = owl_converter.convert_term_type(entity)
            raw_category = term_type_obj.get("type_category")
            if isinstance(raw_category, str):
                term_type_obj["type_category"] = type_category_map.get(
                    raw_category.strip().upper(), raw_category
                )
            type_code = term_type_obj.get("type_code")
            if isinstance(type_code, str) and type_code.strip():
                term_type_map[type_code] = term_type_obj
            converted["term_type"].append(term_type_obj)
            continue

        if entity_type == "term":
            term_obj = owl_converter.convert_term(entity)
            if scope_type in {"object", "view"} and scope_code:
                library_code = str(term_obj.get("library_code") or "").strip()
                term_type_code = str(term_obj.get("term_type_code") or "").strip()
                term_code = str(term_obj.get("term_code") or "").strip()
                parent_term_code = str(term_obj.get("parent_term_code") or "").strip()
                if library_code and term_type_code == "prop":
                    scope_root_term_id = (
                        scope_root_term_id or f"{library_code}#{scope_type}#{scope_code}"
                    )
                    term_obj["parent_term_code"] = scope_code
                    term_obj["parent_term_id"] = scope_root_term_id
                    term_obj["term_id"] = "#".join([scope_root_term_id, term_type_code, term_code])
                elif library_code and parent_term_code:
                    scope_root_term_id = (
                        scope_root_term_id or f"{library_code}#{scope_type}#{scope_code}"
                    )
                    parent_prop_term_id = f"{scope_root_term_id}#prop#{parent_term_code}"
                    term_obj["parent_term_id"] = parent_prop_term_id
                    term_obj["term_id"] = "#".join([parent_prop_term_id, term_type_code, term_code])
            converted["term"].append(term_obj)
            # terms_knowledge 需要拆成独立 knowledge 记录，沿用原有 term_code 外键解析。
            for knowledge_obj in owl_converter.extract_knowledge_records(entity, ""):
                knowledge_obj["term_id"] = term_obj.get("term_id")
                knowledge_obj["term_code"] = term_obj.get("term_code")
                converted["knowledge"].append(knowledge_obj)
            continue

        if entity_type == "relation":
            relation_obj = owl_converter.convert_relation(entity)
            relation_obj["relation_code"] = (
                owl_converter._pick_str(entity, "relation_code")
                or f"{relation_obj.get('source_term_code', '')}/{relation_obj.get('target_term_code', '')}/{relation_obj.get('relation_name', '')}"
            )
            converted["relation"].append(relation_obj)

    return converted


def _collect_scope_root_term_ids(owl_entities: list[dict[str, Any]]) -> list[str]:
    """收集当前 OWL 文件中的 view/object 根 term_id。"""
    root_term_ids: list[str] = []
    seen: set[str] = set()
    for entity in owl_entities:
        entity_type = str(entity.get("entity_type", "")).strip()
        if entity_type not in ("view", "object"):
            continue
        library_code = str(entity.get("library_code") or "").strip()
        term_type_code = str(entity.get("term_type_code") or "").strip()
        term_code = str(entity.get("term_code") or "").strip()
        term_id = (
            f"{library_code}#{term_type_code}#{term_code}"
            if library_code and term_type_code and term_code
            else ""
        )
        if not term_id or term_id in seen:
            continue
        seen.add(term_id)
        root_term_ids.append(term_id)
    return root_term_ids


# 注意：_delete_scope_terms / _delete_scoped_term_names 已迁移到
# BulkImportAdapter.begin_import() 内部实现（adapters/opengauss/import_writer.py）。


def _collect_package_root_term_ids(import_steps: list[dict[str, Any]], root: Path) -> list[str]:
    """收集整个导入包内所有 OWL 文件的 root term_id。"""

    root_term_ids: list[str] = []
    seen: set[str] = set()
    for step in import_steps:
        rel_file = str(step.get("file", "")).strip()
        if not rel_file.endswith(".owl"):
            continue
        path_parts = Path(rel_file).parts
        if len(path_parts) < 3:
            continue
        scope_type, scope_code = path_parts[0], path_parts[1]
        if scope_type not in {"object", "view"}:
            continue
        if not rel_file.endswith("_terms.owl"):
            continue
        owl_entities = owl_parser.parse_owl_file(root / rel_file)
        for entity in owl_entities:
            entity_type = str(entity.get("entity_type", "")).strip()
            if entity_type != "term":
                continue
            if str(entity.get("term_type_code") or "").strip() != scope_type:
                continue
            if str(entity.get("term_code") or "").strip() != scope_code:
                continue
            library_code = str(entity.get("library_code") or "").strip()
            term_id = f"{library_code}#{scope_type}#{scope_code}" if library_code else ""
            if term_id and term_id not in seen:
                seen.add(term_id)
                root_term_ids.append(term_id)
            break
    return root_term_ids


def _collect_package_root_scopes(
    import_steps: list[dict[str, Any]], root: Path
) -> list[dict[str, str]]:
    """收集整个导入包内所有 root scope。"""

    scopes: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for step in import_steps:
        rel_file = str(step.get("file", "")).strip()
        if not rel_file.endswith(".owl"):
            continue
        path_parts = Path(rel_file).parts
        if len(path_parts) < 3:
            continue
        scope_type, scope_code = path_parts[0], path_parts[1]
        if scope_type not in {"object", "view"}:
            continue
        if rel_file.endswith("_terms.owl"):
            key = (scope_type, scope_code)
            if key not in seen:
                seen.add(key)
                scopes.append({"scope": scope_type, "code": scope_code})
    return scopes


# ── 公开入口 ──────────────────────────────────────────────────────────────────


def run(
    folder_path: str,
    *,
    schema: str | None = None,
    db_url: str | None = None,
    conninfo: str | None = None,
) -> dict[str, Any]:
    """按 manifest 顺序在单个事务内导入所有数据。

    数据库访问通过 BulkImportAdapter 完成，本函数负责文件解析和编排。

    Args:
        folder_path: 导入包根目录的本地绝对路径（预检已通过）。

    Returns:
        dict，字段：status / stats / error。

    Raises:
        不抛异常，所有错误封装在返回值 error 字段中。
    """
    root = Path(folder_path)
    stats: dict[str, Any] = {
        "domains": {"inserted": 0, "updated": 0, "deleted": 0},
        "libraries": {"inserted": 0, "updated": 0, "deleted": 0},
        "term_types": {"inserted": 0, "updated": 0, "deleted": 0},
        "terms": {"inserted": 0, "updated": 0, "deleted": 0},
        "relations": {"inserted": 0, "updated": 0, "deleted": 0},
        "knowledge": {"inserted": 0, "updated": 0, "deleted": 0},
    }

    manifest_path = root / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        import_steps: list[dict[str, Any]] = manifest.get("import_steps", [])
    else:
        import_steps = [
            {"type": step_type, "file": str(path.relative_to(root))}
            for step_type, path in discover_owl_files(root)
        ]
        logger.info("manifest.json 不存在，已切换到目录扫描模式: %s 个 OWL 文件", len(import_steps))

    adapter = create_bulk_importer(schema=schema, db_url=db_url, conninfo=conninfo)
    try:
        adapter.begin_import(
            scopes=_collect_package_root_scopes(import_steps, root),
            root_term_ids=_collect_package_root_term_ids(import_steps, root),
        )
        for step in import_steps:
            rel_file: str = step.get("file", "")
            step_type: str = step.get("type", "")
            entity_type = _step_entity_type(step_type, rel_file)
            batch_method = _STEP_BATCH_METHODS.get(entity_type)
            if batch_method is None and step_type != "ontology":
                logger.warning("未知 step type '%s', 跳过 %s", step_type, rel_file)
                continue
            if step_type == "ontology":
                logger.info("ontology %s (reference file, parse but skip DB)", rel_file)
                continue

            file_path = root / rel_file
            logger.info("importing %s (%s)", rel_file, entity_type)
            if rel_file.endswith(".owl"):
                owl_entities = owl_parser.parse_owl_file(file_path)
                converted = _convert_owl_entities(step_type, rel_file, owl_entities)
                for entity_type_key, objs in converted.items():
                    if not objs:
                        continue
                    method_name = _STEP_BATCH_METHODS.get(entity_type_key)
                    if method_name is None:
                        logger.warning(
                            "OWL 实体类型 '%s', 无处理器, 跳过 %s", entity_type_key, rel_file
                        )
                        continue
                    getattr(adapter, method_name)(objs, stats)
            else:
                logger.warning("不支持的文件扩展名, 跳过 %s", rel_file)

        adapter.commit()
        logger.info("import committed: %s", stats)
        return {"status": "success", "stats": stats, "error": None}

    except Exception as exc:
        adapter.rollback()
        logger.exception("import failed, rolled back")
        return {"status": "failed", "stats": stats, "error": str(exc)}
    finally:
        adapter.close()
