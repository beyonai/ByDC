"""Convert 亦庄术语库导入文件 (Excel) to dict_terms.jsonl and list_terms.jsonl.

Reads Excel files from docs/亦庄术语库导入文件/:
- 字典术语-*.xlsx -> terms with domain DOMAIN_002, library LIB_002 -> dict_terms.jsonl
- 列表术语-*.xlsx -> terms with domain DOMAIN_002, library LIB_002 -> list_terms.jsonl

Expects Excel columns: 术语编码, 术语名称, 术语类型, 术语描述, 父编码, ...
Rows with 父编码=-1 are type definitions (skipped for term output).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# Output binding
DOMAIN_CODE = "DOMAIN_002"
LIBRARY_CODE = "LIB_002"

# Column names in source Excel (fallback: use iloc 0,1,2)
COL_CODE = "术语编码"
COL_NAME = "术语名称"
COL_TYPE = "术语类型"  # parent type; -1 = type-def row
IDX_CODE, IDX_NAME, IDX_TYPE = 0, 1, 2


def _parent_term_code(type_code: str) -> str:
    """Build parent_term_code from term_type_code."""
    return f"TERM_TYPE_{type_code.upper()}"


def _load_excel(path: Path) -> pd.DataFrame:
    """Load Excel and normalize column types."""
    return pd.read_excel(path)


def _get_val(row: pd.Series, df: pd.DataFrame, col: str, idx: int):
    """Get value by column name or index (handles encoding)."""
    if col in df.columns:
        return row.get(col)
    if idx < len(row):
        return row.iloc[idx]
    return None


def _extract_terms(df: pd.DataFrame) -> list[dict]:
    """Extract term rows (skip type-def rows where 术语类型 is -1)."""
    terms = []
    for _, row in df.iterrows():
        type_val = _get_val(row, df, COL_TYPE, IDX_TYPE)
        if pd.isna(type_val) or type_val is None:
            continue
        if type_val == -1 or type_val == "-1" or str(type_val).strip() == "-1":
            continue
        code = _get_val(row, df, COL_CODE, IDX_CODE)
        name = _get_val(row, df, COL_NAME, IDX_NAME)
        if pd.isna(code) or pd.isna(name) or str(code).strip() == "":
            continue
        code = str(code).strip()
        name = str(name).strip()
        type_code = str(type_val).strip()
        terms.append(
            {
                "op": "add",
                "term_code": code,
                "term_name": name,
                "term_type_code": type_code,
                "domain_code": DOMAIN_CODE,
                "library_code": LIBRARY_CODE,
                "parent_term_code": _parent_term_code(type_code),
            }
        )
    return terms


def _collect_from_dir(
    base: Path,
    pattern: str,
) -> list[dict]:
    """Collect terms from all matching Excel files."""
    all_terms: list[dict] = []
    seen_codes: set[str] = set()
    files = sorted(base.glob(pattern))
    for p in files:
        try:
            df = _load_excel(p)
            terms = _extract_terms(df)
            for t in terms:
                if t["term_code"] not in seen_codes:
                    seen_codes.add(t["term_code"])
                    all_terms.append(t)
            logger.info("Loaded %s: %d terms", p.name, len(terms))
        except Exception as e:
            logger.warning("Skip %s: %s", p.name, e)
    return all_terms


def _extract_type_defs(df: pd.DataFrame) -> list[tuple[str, str]]:
    """Extract type definitions (rows where 术语类型=-1). Returns [(type_code, type_name)]."""
    result = []
    for _, row in df.iterrows():
        type_val = _get_val(row, df, COL_TYPE, IDX_TYPE)
        if pd.isna(type_val) or type_val is None:
            continue
        if type_val != -1 and type_val != "-1" and str(type_val).strip() != "-1":
            continue
        code = _get_val(row, df, COL_CODE, IDX_CODE)
        name = _get_val(row, df, COL_NAME, IDX_NAME)
        if pd.isna(code) or str(code).strip() == "":
            continue
        result.append((str(code).strip(), str(name).strip() if not pd.isna(name) else ""))
    return result


def _update_term_types(docs_dir: Path, term_types_path: Path) -> None:
    """Append 亦庄 term types to custom.jsonl if not already present."""
    existing: set[str] = set()
    lines: list[str] = []
    if term_types_path.exists():
        with open(term_types_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if line:
                    lines.append(line)
                    try:
                        obj = json.loads(line)
                        if obj.get("op") == "add" and "type_code" in obj:
                            existing.add(obj["type_code"])
                    except json.JSONDecodeError:
                        pass

    added = 0
    for pattern, category in [("字典术语-*.xlsx", "字典术语"), ("列表术语-*.xlsx", "列表术语")]:
        for p in sorted(docs_dir.glob(pattern)):
            try:
                df = _load_excel(p)
                for type_code, type_name in _extract_type_defs(df):
                    if type_code not in existing:
                        existing.add(type_code)
                        lines.append(
                            json.dumps(
                                {
                                    "op": "add",
                                    "type_code": type_code,
                                    "type_name": type_name or type_code,
                                    "type_desc": f"{type_name or type_code}类型",
                                    "type_category": category,
                                    "is_builtin": False,
                                },
                                ensure_ascii=False,
                            )
                        )
                        added += 1
            except Exception as e:
                logger.warning("Skip %s for term_types: %s", p.name, e)

    if added > 0:
        with open(term_types_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        logger.info("Appended %d term types -> %s", added, term_types_path)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    script_dir = Path(__file__).resolve().parent
    mock_root = script_dir.parent
    docs_dir = mock_root / "docs" / "亦庄术语库导入文件"
    out_dir = mock_root / "resource" / "knowledge" / "import_package" / "terms"
    term_types_path = mock_root / "resource" / "knowledge" / "import_package" / "term_types" / "custom.jsonl"

    if not docs_dir.exists():
        logger.error("Source dir not found: %s", docs_dir)
        return

    # Dict terms
    dict_terms = _collect_from_dir(docs_dir, "字典术语-*.xlsx")
    dict_path = out_dir / "dict_terms.jsonl"
    with open(dict_path, "w", encoding="utf-8") as f:
        for t in dict_terms:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    logger.info("Wrote %d dict terms -> %s", len(dict_terms), dict_path)

    # List terms
    list_terms = _collect_from_dir(docs_dir, "列表术语-*.xlsx")
    list_path = out_dir / "list_terms.jsonl"
    with open(list_path, "w", encoding="utf-8") as f:
        for t in list_terms:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    logger.info("Wrote %d list terms -> %s", len(list_terms), list_path)

    # Update term_types
    _update_term_types(docs_dir, term_types_path)


if __name__ == "__main__":
    main()
