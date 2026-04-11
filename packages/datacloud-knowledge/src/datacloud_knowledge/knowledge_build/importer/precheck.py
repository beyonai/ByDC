"""知识包预检：全内存校验，不写数据库。

校验顺序：
  1. manifest.json 存在且合法
  2. manifest 中每个文件均存在
  3. 每个 JSONL 文件：每行为合法 JSON 对象
  4. 必填字段校验（各实体类型规则不同）
  5. 包内交叉引用（terms 引用的 domain_code / library_code / term_type_code 均已定义）
  6. relations 引用的 source/target term_code 均已定义
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)

# ── 必填字段规则 ──────────────────────────────────────────────────────────────

_REQUIRED: dict[str, list[str]] = {
    "meta_domain": ["domain_code", "domain_name"],
    "meta_library": ["library_code", "library_name"],
    "term_type": ["type_code", "type_name", "type_category"],
    "term": ["term_code", "term_name", "term_type_code", "domain_code"],
    "relation": ["relation_code", "source_term_code", "target_term_code", "relation_name"],
    "knowledge": ["knowledge_id", "term_code"],
}

# 内置 term_type_code，无需在导入包中定义
_BUILTIN_TYPE_CODES: frozenset[str] = frozenset(
    {
        "employee",
        "general",
        "view",
        "object",
        "action",
        "func",
        "param",
        "prop",
    }
)


def _step_entity_type(step_type: str, filename: str) -> str:
    """根据 manifest step type 和文件名推断实体类型 key。"""
    if step_type == "meta":
        if "domain" in filename:
            return "meta_domain"
        return "meta_library"
    if step_type == "term_types":
        return "term_type"
    if step_type == "terms":
        return "term"
    if step_type == "relations":
        return "relation"
    return step_type


def run(folder_path: str) -> dict[str, Any]:
    """执行预检，返回结构化结果 dict（与 PrecheckResult 对应）。

    Args:
        folder_path: 导入包根目录的本地绝对路径。

    Returns:
        dict，字段：status / total_rows / files / errors。
    """
    root = Path(folder_path)
    all_errors: list[dict[str, Any]] = []
    file_results: list[dict[str, Any]] = []
    total_rows = 0

    # ── Step 1：manifest 检查 ────────────────────────────────────────────────
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        return {
            "status": "failed",
            "total_rows": 0,
            "files": [],
            "errors": [{"file": "manifest.json", "line": None, "error": "文件不存在"}],
        }

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "status": "failed",
            "total_rows": 0,
            "files": [],
            "errors": [{"file": "manifest.json", "line": None, "error": f"JSON 解析失败: {exc}"}],
        }

    import_steps: list[dict[str, Any]] = manifest.get("import_steps", [])
    if not import_steps:
        return {
            "status": "failed",
            "total_rows": 0,
            "files": [],
            "errors": [{"file": "manifest.json", "line": None, "error": "import_steps 为空"}],
        }

    # ── Step 1.5：校验 ontology 文件不允许入库 ────────────────────────────────
    ontology_errors = _validate_no_ontology_steps(manifest)
    if ontology_errors:
        return {
            "status": "failed",
            "total_rows": 0,
            "files": [],
            "errors": ontology_errors,
        }
    if not import_steps:
        return {
            "status": "failed",
            "total_rows": 0,
            "files": [],
            "errors": [{"file": "manifest.json", "line": None, "error": "import_steps 为空"}],
        }

    # ── 收集包内已定义的 code，用于交叉引用校验 ───────────────────────────────
    defined_domain_codes: set[str] = set()
    defined_library_codes: set[str] = set()
    defined_type_codes: set[str] = set(_BUILTIN_TYPE_CODES)
    defined_term_codes: set[str] = set()

    # 两轮扫描：第一轮收集所有定义，第二轮做交叉引用校验
    # 为简化，先全量解析 JSONL 存入内存，再统一校验
    parsed_steps: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []  # (step, rows)

    for step in import_steps:
        rel_file: str = step.get("file", "")
        step_type: str = step.get("type", "")
        file_path = root / rel_file
        file_errors: list[dict[str, Any]] = []
        rows: list[dict[str, Any]] = []

        # ── Step 2：文件存在性 ──────────────────────────────────────────────
        if not file_path.exists():
            all_errors.append({"file": rel_file, "line": None, "error": "文件不存在"})
            file_results.append(
                {
                    "file": rel_file,
                    "rows": 0,
                    "errors": [
                        {"file": rel_file, "line": None, "error": "文件不存在"},
                    ],
                }
            )
            parsed_steps.append((step, []))
            continue

        entity_type = _step_entity_type(step_type, rel_file)

        # ── Step 2.5：按扩展名路由 ──────────────────────────────────────────
        # OWL 文件跳过 JSONL 解析，只做文件存在性检查
        if rel_file.endswith(".owl"):
            file_results.append({"file": rel_file, "rows": 0, "errors": []})
            parsed_steps.append((step, []))
            continue

        # ── Step 3 & 4：JSONL 格式 + 必填字段 ──────────────────────────────

        # ── Step 3 & 4：JSONL 格式 + 必填字段 ──────────────────────────────
        required_fields = _REQUIRED.get(entity_type, [])
        for lineno, raw_line in enumerate(
            file_path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            line = raw_line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                err = {"file": rel_file, "line": lineno, "error": f"JSON 格式错误: {exc}"}
                file_errors.append(err)
                all_errors.append(err)
                continue

            # 必填字段
            for field in required_fields:
                if not obj.get(field):
                    err = {"file": rel_file, "line": lineno, "error": f"缺少必填字段: {field}"}
                    file_errors.append(err)
                    all_errors.append(err)

            rows.append(obj)

        # 收集定义集合（第一轮，仅 add 操作）
        for obj in rows:
            if obj.get("op", "add") != "add":
                continue
            if entity_type == "meta_domain":
                if code := obj.get("domain_code"):
                    defined_domain_codes.add(code)
            elif entity_type == "meta_library":
                if code := obj.get("library_code"):
                    defined_library_codes.add(code)
            elif entity_type == "term_type":
                if code := obj.get("type_code"):
                    defined_type_codes.add(code)
            elif entity_type == "term":
                if code := obj.get("term_code"):
                    defined_term_codes.add(code)

        row_count = len(rows)
        total_rows += row_count
        file_results.append({"file": rel_file, "rows": row_count, "errors": file_errors})
        parsed_steps.append((step, rows))

    # ── Step 5 & 6：交叉引用校验 ─────────────────────────────────────────────
    for step, rows in parsed_steps:
        rel_file = step.get("file", "")
        step_type = step.get("type", "")
        entity_type = _step_entity_type(step_type, rel_file)

        if entity_type not in ("term", "relation", "knowledge"):
            continue

        for lineno, obj in enumerate(rows, start=1):
            op = obj.get("op", "add")
            if op == "delete":
                continue

            if entity_type == "term":
                domain_code = obj.get("domain_code")
                if domain_code and domain_code not in defined_domain_codes:
                    err = {
                        "file": rel_file,
                        "line": lineno,
                        "error": f"domain_code '{domain_code}' 未在 meta/domains.jsonl 中定义(也不在数据库中)",
                    }
                    all_errors.append(err)
                    # 同步更新 file_results
                    _append_file_error(file_results, rel_file, err)

                lib_code = obj.get("library_code")
                if lib_code and lib_code not in defined_library_codes:
                    err = {
                        "file": rel_file,
                        "line": lineno,
                        "error": f"library_code '{lib_code}' 未在 meta/libraries.jsonl 中定义(也不在数据库中)",
                    }
                    all_errors.append(err)
                    _append_file_error(file_results, rel_file, err)

                type_code = obj.get("term_type_code")
                if type_code and type_code not in defined_type_codes:
                    err = {
                        "file": rel_file,
                        "line": lineno,
                        "error": f"term_type_code '{type_code}' 未定义(非内置类型，也未在 term_types/ 中定义)",
                    }
                    all_errors.append(err)
                    _append_file_error(file_results, rel_file, err)

            elif entity_type == "relation":
                for field in ("source_term_code", "target_term_code"):
                    code = obj.get(field)
                    if code and code not in defined_term_codes:
                        err = {
                            "file": rel_file,
                            "line": lineno,
                            "error": f"{field} '{code}' 未在 terms/ 文件中定义(也不在数据库中)",
                        }
                        all_errors.append(err)
                        _append_file_error(file_results, rel_file, err)

            elif entity_type == "knowledge":
                term_code = obj.get("term_code")
                if term_code and term_code not in defined_term_codes:
                    err = {
                        "file": rel_file,
                        "line": lineno,
                        "error": f"term_code '{term_code}' 未在 terms/ 文件中定义(也不在数据库中)",
                    }
                    all_errors.append(err)
                    _append_file_error(file_results, rel_file, err)
    status = "failed" if all_errors else "ok"
    logger.info("precheck %s: %d rows, %d errors", status, total_rows, len(all_errors))
    return {
        "status": status,
        "total_rows": total_rows,
        "files": file_results,
        "errors": all_errors,
    }


def _validate_no_ontology_steps(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """校验 manifest.import_steps 中不允许出现 ontology/ 目录下的文件。

    Args:
        manifest: 已解析的 manifest.json 字典。

    Returns:
        错误列表，每个错误格式: {"code": "INVALID_ONTOLOGY_STEP", "message": "...", "file": "..."}
    """
    errors: list[dict[str, Any]] = []
    import_steps: list[dict[str, Any]] = manifest.get("import_steps", [])

    for step in import_steps:
        file_path: str = step.get("file", "")
        if file_path.startswith("ontology/"):
            errors.append(
                {
                    "code": "INVALID_ONTOLOGY_STEP",
                    "message": f"ontology 文件不允许入库: {file_path}",
                    "file": file_path,
                }
            )

    return errors


def _append_file_error(
    file_results: list[dict[str, Any]], rel_file: str, err: dict[str, Any]
) -> None:
    """向 file_results 中对应文件追加一条错误（避免重复遍历）。"""
    for fr in file_results:
        if fr["file"] == rel_file:
            fr["errors"].append(err)
            return
