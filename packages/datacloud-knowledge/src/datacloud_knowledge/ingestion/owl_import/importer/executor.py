"""知识包入库执行器：按 manifest 顺序在单个事务内写入数据库。

环境变量 DATACLOUD_KNOWLEDGE_IMPORT_BATCH_SIZE（默认 500，上限 10000）控制每个文件按批解析并入库的行数，减少与数据库的往返次数。

前提：调用方已通过 ingestion/validate.check_package() 校验，此处不再做格式校验。
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

from . import inference, owl_converter, owl_parser

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
    """将 OWL 解析结果转换为各批处理器可消费的数据结构。

    Task 1.8 改造：使用 KPS 版本转换器（convert_*_to_kps）产出 typed dataclass，
    再通过 kps_to_dict 序列化函数转为 writer 层兼容的 dict。
    """
    del step_type

    converted: dict[str, list[dict[str, Any]]] = {
        "meta_domain": [],
        "meta_library": [],
        "term_type": [],
        "term": [],
        "relation": [],
        "knowledge": [],
    }
    # term_type_map 按 type_code 索引已转换的术语类型（KPS TermTypeDef 对象）
    term_type_map: dict[str, Any] = {}

    # 从文件路径提取 scope 信息（object/ 或 view/ 目录下的子目录名）
    path_parts = Path(rel_file).parts
    scope_type = path_parts[0] if len(path_parts) >= 2 else ""
    scope_code = path_parts[1] if len(path_parts) >= 2 else ""
    scope_root_term_id: str | None = None

    # 第一遍扫描：找到当前文件的 root term（scope 对象/视图的根术语）
    for entity in owl_entities:
        if str(entity.get("entity_type", "")).strip() != "term":
            continue
        if str(entity.get("term_type_code") or "").strip() != scope_type:
            continue
        if str(entity.get("term_code") or "").strip() != scope_code:
            continue
        # parser 输出无 term_id 字段，从 library_code + type_code + code 拼接
        lib = str(entity.get("library_code") or "").strip()
        if lib:
            scope_root_term_id = f"{lib}#{scope_type}#{scope_code}"
            break

    for entity in owl_entities:
        entity_type = str(entity.get("entity_type", "")).strip()
        if not entity_type:
            continue

        # ── Domain：KPS 转换 → dict ──────────────────────────────────
        if entity_type == "domain":
            domain_def = owl_converter.convert_domain_to_kps(entity)
            converted["meta_domain"].append(owl_converter.domain_kps_to_dict(domain_def))
            continue

        # ── Library：KPS 转换 → dict（原为 executor 内联构造）────────
        if entity_type == "library":
            library_def = owl_converter.convert_library_to_kps(entity)
            if library_def.library_code:
                converted["meta_library"].append(owl_converter.library_kps_to_dict(library_def))
            continue

        # ── TermType：KPS 转换 → dict（消除 string↔int 来回映射）────
        if entity_type == "term_type":
            term_type_def = owl_converter.convert_term_type_to_kps(entity)
            if term_type_def.type_code.strip():
                term_type_map[term_type_def.type_code] = term_type_def
            converted["term_type"].append(owl_converter.term_type_kps_to_dict(term_type_def))
            continue

        # ── Term：KPS 转换 + scope 处理 → dict ───────────────────────
        if entity_type == "term":
            term_def, extras = owl_converter.convert_term_to_kps(entity)

            # scope 处理：根据文件所在目录层级计算正确的 term_id / parent_term_id
            # 逻辑与旧版完全一致，仅输入从 dict 改为 KPS frozen dataclass
            if scope_type in {"object", "view"} and scope_code:
                library_code = term_def.library_code
                term_type_code = term_def.term_type_code
                term_code = term_def.term_code
                parent_term_code = term_def.parent_term_code or ""

                if library_code and term_type_code == "prop":
                    # prop 术语：parent 指向 scope 对象/视图
                    scope_root = scope_root_term_id or f"{library_code}#{scope_type}#{scope_code}"
                    # 覆盖 parent_term_code 为 scope_code（与旧版行为一致）
                    term_id = f"{scope_root}#{term_type_code}#{term_code}"
                    parent_term_id: str | None = scope_root
                    # 修改 parent_term_code 为 scope_code（scope 处理需要）
                    overridden_parent = scope_code
                elif library_code and parent_term_code:
                    # 值术语（如 LIST_TERM）：parent 指向上层 prop
                    scope_root = scope_root_term_id or f"{library_code}#{scope_type}#{scope_code}"
                    parent_prop_term_id = f"{scope_root}#prop#{parent_term_code}"
                    term_id = f"{parent_prop_term_id}#{term_type_code}#{term_code}"
                    parent_term_id = parent_prop_term_id
                    overridden_parent = None  # 保持 OWL 中的 parent_term_code
                else:
                    # 根术语或非 scope 术语：使用 compute_term_id
                    term_id = term_def.compute_term_id()
                    parent_term_id = None
                    overridden_parent = None
            else:
                term_id = term_def.compute_term_id()
                parent_term_id = None
                overridden_parent = None

            # 序列化为 writer dict
            writer_dict = owl_converter.term_kps_to_dict(
                term_def, extras, term_id=term_id, parent_term_id=parent_term_id
            )
            # 若 scope 处理覆盖了 parent_term_code，反映到 dict 中
            if overridden_parent is not None:
                writer_dict["parent_term_code"] = overridden_parent
            converted["term"].append(writer_dict)

            # terms_knowledge 拆分：从术语实体的 terms_knowledge 字段提取 knowledge 记录
            for knowledge_obj in owl_converter.extract_knowledge_records(entity, ""):
                knowledge_obj["term_id"] = term_id
                knowledge_obj["term_code"] = term_def.term_code
                converted["knowledge"].append(knowledge_obj)
            continue

        # ── Relation：KPS 转换 → dict（修正 relation_category/cardinality）────────
        if entity_type == "relation":
            rel_def = owl_converter.convert_relation_to_kps(entity)
            relation_code = (
                owl_converter._pick_str(entity, "relation_code")
                or f"{rel_def.source_term_code}/{rel_def.target_term_code}/{rel_def.relation_name}"
            )
            writer_dict = owl_converter.relation_kps_to_dict(rel_def, relation_code=relation_code)

            # 根据 scope 上下文解析层级 term_id（与 prop 术语处理一致）
            # source 始终是根术语，term_id 即 source_term_code
            writer_dict["source_term_id"] = rel_def.source_term_code
            # target：若为 prop 且在 object/view scope 下，计算层级 term_id
            target_parts = rel_def.target_term_code.rsplit("#", 2)
            if (
                len(target_parts) == 3
                and target_parts[1] == "prop"
                and scope_type in {"object", "view"}
            ):
                # 从 source_term_code 提取 library_code 以构建 scope root
                lib = rel_def.source_term_code.split("#", 1)[0]
                if lib:
                    scope_root = f"{lib}#{scope_type}#{scope_code}"
                    writer_dict["target_term_id"] = f"{scope_root}#prop#{target_parts[2]}"

            converted["relation"].append(writer_dict)

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
                owl_entities = inference.normalize_entities(owl_entities)
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
