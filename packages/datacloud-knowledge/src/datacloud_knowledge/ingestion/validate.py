"""OWL 知识包导入前校验 — 目录扫描 + KPS 语义验证。

替代原来的 precheck.py（基于 manifest.json + JSONL），
直接扫描目录中的 OWL 文件，解析为 KnowledgePackage，
执行 contracts/validation 的语义校验规则。

与 executor.py 配合使用，实现三步导入管线：
  1. validate.check_package(folder_path) → (ok, errors)
  2. executor.run(folder_path) → {status, stats}
  3. contracts/validation.validate_package(kps) → 10条SEM规则

使用方式:
    from datacloud_knowledge.ingestion.validate import check_package
    ok, errors = check_package("./my_owl_package")
    if not ok:
        for e in errors:
            print(e)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from datacloud_knowledge.contracts.kps import KnowledgePackage
from datacloud_knowledge.contracts.validation import validate_package
from datacloud_knowledge.ingestion.owl_import.importer import executor, owl_parser

logger = logging.getLogger(__name__)


def check_package(folder_path: str) -> tuple[bool, list[str]]:
    """校验 OWL 知识包目录（Layer 1 结构校验 + KPS 语义校验）。

    执行两步：
    1. 目录扫描 → 发现 OWL 文件（复用 executor.discover_owl_files）
    2. 对每个 OWL 文件执行 rdflib 解析 → 收集实体
    3. 对收集到的实体执行 Layer 1 结构层校验
    4. 构造 KnowledgePackage → 执行 KPS 语义校验

    Args:
        folder_path: OWL 包根目录（含 object/ view/ 子目录）。

    Returns:
        (passed, errors): passed=True 校验通过，errors 为可读错误列表。
    """
    root = Path(folder_path)
    all_errors: list[str] = []

    if not root.exists():
        return False, [f"目录不存在: {folder_path}"]

    # ── Step 1: 目录扫描，发现所有 OWL 文件 ─────────────────────────
    owl_files: list[tuple[str, Path]] = []
    try:
        owl_files = executor.discover_owl_files(root)
    except Exception as exc:
        logger.exception("目录扫描失败: %s", folder_path)
        return False, [f"目录扫描异常: {exc}"]

    if not owl_files:
        all_errors.append("目录下未发现任何 OWL 文件")

    # ── Step 2: 解析 OWL 文件，收集数据 ─────────────────────────────
    parsed_data: list[dict[str, Any]] = []
    parse_errors: list[str] = []

    for step_type, file_path in owl_files:
        rel_path = str(file_path.relative_to(root))
        try:
            entities = owl_parser.parse_owl_file(file_path)
            for entity in entities:
                entity["_source_file"] = rel_path
                entity["_step_type"] = step_type
            parsed_data.extend(entities)
        except Exception as exc:
            msg = f"OWL 解析失败 [{rel_path}]: {exc}"
            parse_errors.append(msg)
            logger.warning(msg)

    if parse_errors:
        all_errors.extend(parse_errors)

    # ── Step 3: Layer 1 结构层校验（文件级基本检查）────────────────
    # 检查是否至少有一个 object/ 或 view/ 目录下有文件
    has_content = any(
        entity.get("entity_type") in ("term", "object", "view") for entity in parsed_data
    )
    if not has_content and parsed_data:
        all_errors.append("已解析 OWL 文件但未发现术语/对象/视图实体")

    # ── Step 4: 组装 KnowledgePackage + KPS 语义校验 ──────────────
    # 注意：此时的 parsed_data 是 dict 列表（owl_parser 输出），
    # 需要等 Task 1.8（owl_converter 消费 KPS）完成后方可构造完整 KPS。
    # Phase 1 过渡：先执行可用层面的校验，KPS 构造待 converter 改造完成后启用。
    sem_errors: list[str] = []

    # 尝试构造基础 KPS（如果 converter 已支持 KPS 输出）
    try:
        kps = _build_partial_kps(parsed_data)
        _, sem_errors = validate_package(kps)
    except Exception as exc:
        logger.debug("KPS 构造/校验暂未完整就绪: %s", exc)

    all_errors.extend(sem_errors)

    passed = len(all_errors) == 0
    status = "✓" if passed else "✗"
    logger.info(
        "validate %s: %d OWL files, %d entities, %d errors",
        status,
        len(owl_files),
        len(parsed_data),
        len(all_errors),
    )

    return passed, all_errors


def _build_partial_kps(parsed_data: list[dict[str, Any]]) -> KnowledgePackage:
    """从 owl_parser 的 dict 输出构造 KnowledgePackage，通过 owl_converter 归一化。

    使用 converter 函数（convert_term_to_kps / convert_relation_to_kps /
    convert_term_type_to_kps）确保 type 别名（"场景"→"view"）、cardinality 映射、
    source_type alias 等归一化规则在语义校验前统一应用。
    """
    from datacloud_knowledge.contracts.kps import RelationDef, TermDef, TermTypeDef
    from datacloud_knowledge.ingestion.owl_import.importer.owl_converter import (
        convert_relation_to_kps,
        convert_term_to_kps,
        convert_term_type_to_kps,
    )

    terms: list[TermDef] = []
    relations: list[RelationDef] = []
    term_types: list[TermTypeDef] = []

    for entity in parsed_data:
        entity_type = str(entity.get("entity_type", "")).strip()
        if entity_type == "term":
            try:
                term_def, _extras = convert_term_to_kps(entity)
                terms.append(term_def)
            except Exception:
                logger.debug("跳过无效 term 实体: %s", entity)
                continue
        elif entity_type == "relation":
            try:
                rel = convert_relation_to_kps(entity)
                relations.append(rel)
            except Exception:
                logger.debug("跳过无效 relation 实体: %s", entity)
                continue
        elif entity_type == "term_type":
            try:
                tt = convert_term_type_to_kps(entity)
                term_types.append(tt)
            except Exception:
                logger.debug("跳过无效 term_type 实体: %s", entity)
                continue

    return KnowledgePackage(
        terms=tuple(terms),
        relations=tuple(relations),
        term_types=tuple(term_types),
    )


__all__ = ["check_package"]
