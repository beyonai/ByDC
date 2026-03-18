"""将 mock_env CSV / ontology 数据转换为标准导入包格式（JSONL）。

输出目录：
    examples/sales_analysis_demo/mock_env/resource/knowledge/import_package/

运行：
    python examples/sales_analysis_demo/mock_env/resource/knowledge/_gen_import_package.py
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

# ── 路径 ──────────────────────────────────────────────────────────────────────
_ROOT     = Path(__file__).resolve().parents[5]   # whale_datacloud 根目录
_BASE     = Path(__file__).parent
_OUTPUT   = _BASE / "import_package"

_BASE_DIR = _BASE / "base"
_TERM_DIR = _BASE / "terminology"
_ONTO_DIR = _BASE / "ontology"

# ── 类型映射 ──────────────────────────────────────────────────────────────────
# term.csv 旧 type_code → 系统内置 type_code
_TYPE_CODE_MAP = {
    "OBJ":    "ONTOLOGY_OBJ",
    "VIEW":   "ONTOLOGY_VIEW",
    "ACTION": "ONTOLOGY_ACTION",
    "FUNC":   "ONTOLOGY_FUNC",
}

# term_data 中已有对应概念术语（term.csv 已定义），直接复用
_TYPE_TO_EXISTING_CONCEPT = {
    "orgName":   "TERM_ORG",   # TERM_ORG 已在 term.csv
    "staffName": "TERM_EMP",   # TERM_EMP 已在 term.csv
}

# ── 工具函数 ──────────────────────────────────────────────────────────────────
def _read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            # 去掉值为 None 或空字符串的可选字段
            cleaned = {k: v for k, v in r.items() if v is not None and v != ""}
            f.write(json.dumps(cleaned, ensure_ascii=False) + "\n")
    print(f"  written {len(records):4d} rows → {path.relative_to(_BASE)}")


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  written        → {path.relative_to(_BASE)}")


def _onto_name(data: dict, subdir: str, stem: str) -> tuple[str, str, str]:
    """返回 (term_code, term_name, desc_summary)。"""
    if subdir == "objects":
        return (
            data.get("object_code", stem),
            data.get("object_name", stem),
            data.get("description", ""),
        )
    if subdir == "views":
        return (
            data.get("view_id", stem),
            data.get("view_name", stem),
            data.get("description", ""),
        )
    if subdir == "actions":
        return (
            stem,
            data.get("action_name", stem),
            data.get("description", ""),
        )
    if subdir == "functions":
        return (
            stem,
            data.get("func_name", data.get("function_name", data.get("name", stem))),
            data.get("description", ""),
        )
    return stem, stem, ""


# ── 各文件生成 ─────────────────────────────────────────────────────────────────
def gen_meta() -> None:
    print("\n[meta]")
    domains = _read_csv(_BASE_DIR / "domain.csv")
    _write_jsonl(_OUTPUT / "meta/domains.jsonl", [
        {
            "op":          "add",
            "domain_code": d["domain_id"],
            "domain_name": d["domain_name"],
            "parent_code": d["parent_id"] or None,
            "domain_desc": d.get("domain_desc", ""),
        }
        for d in domains
    ])

    libraries = _read_csv(_BASE_DIR / "term_library.csv")
    _write_jsonl(_OUTPUT / "meta/libraries.jsonl", [
        {
            "op":           "add",
            "library_code": lib["library_id"],
            "library_name": lib["library_name"],
        }
        for lib in libraries
    ])


def gen_term_types(term_data: list[dict]) -> list[dict]:
    """生成自定义术语类型，返回类型列表供后续使用。"""
    print("\n[term_types]")
    seen: dict[str, dict] = {}
    for row in term_data:
        tt = row["term_type"]
        if tt not in seen:
            category = "列表术语" if row["term_data_type"] == "list" else "字典术语"
            seen[tt] = {
                "op":            "add",
                "type_code":     tt,
                "type_name":     row["term_type_name"],
                "type_desc":     f"{row['term_type_name']}类型",
                "type_category": category,
                "is_builtin":    False,
            }

    # DOC 类型来自 term.csv，不在 term_data 中
    seen["DOC"] = {
        "op":            "add",
        "type_code":     "DOC",
        "type_name":     "文档",
        "type_desc":     "文档名称术语，用于关联外部文档",
        "type_category": "文档名称术语",
        "is_builtin":    False,
    }

    records = list(seen.values())
    _write_jsonl(_OUTPUT / "term_types/custom.jsonl", records)
    return records


def gen_concept_terms(term_data: list[dict]) -> None:
    """生成概念术语：term.csv 条目 + 每个自定义类型对应的概念。"""
    print("\n[terms/concept_terms]")
    entries: list[dict] = []
    seen_codes: set[str] = set()

    # A. term.csv 的条目
    for t in _read_csv(_TERM_DIR / "term.csv"):
        type_code  = _TYPE_CODE_MAP.get(t["term_type_code"], t["term_type_code"])
        domain_id  = t["domain_id"] if t["domain_id"] != "DOMAIN_003" else "DOMAIN_001"
        parent     = "TERM_EMP" if t["term_type_code"] == "EMPLOYEE" else None
        entry = {
            "op":           "add",
            "term_code":    t["term_id"],
            "term_name":    t["term_name"],
            "term_type_code": type_code,
            "domain_code":  domain_id,
            "library_code": t["library_id"],
            "parent_term_code": parent,
            "desc_summary": t.get("desc_summary", ""),
        }
        entries.append(entry)
        seen_codes.add(t["term_id"])

    # B. 每个自定义类型对应的概念术语（不重复）
    seen_types: set[str] = set()
    for row in term_data:
        tt = row["term_type"]
        if tt in seen_types:
            continue
        seen_types.add(tt)

        if tt in _TYPE_TO_EXISTING_CONCEPT:
            continue   # 已有对应概念，跳过

        concept_code = f"TERM_TYPE_{tt.upper()}"
        if concept_code in seen_codes:
            continue

        tc = "ONTOLOGY_OBJ" if row["term_data_type"] == "list" else "GENERAL"
        entries.append({
            "op":           "add",
            "term_code":    concept_code,
            "term_name":    row["term_type_name"],
            "term_type_code": tc,
            "domain_code":  "DOMAIN_001",
            "library_code": "LIB_003",
            "desc_summary": f"{row['term_type_name']}概念术语",
        })
        seen_codes.add(concept_code)

    _write_jsonl(_OUTPUT / "terms/concept_terms.jsonl", entries)


def gen_list_and_dict_terms(term_data: list[dict]) -> dict[str, int]:
    """生成列表术语和字典术语，返回 {文件名: 行数} 供 manifest 使用。"""
    print("\n[terms/list & dict]")
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in term_data:
        groups[row["term_type"]].append(row)

    counts: dict[str, int] = {}

    list_types = {tt for tt, rows in groups.items() if rows[0]["term_data_type"] == "list"}

    # 按类型生成列表术语文件
    for tt in sorted(list_types):
        rows   = groups[tt]
        parent = _TYPE_TO_EXISTING_CONCEPT.get(tt, f"TERM_TYPE_{tt.upper()}")
        entries = [
            {
                "op":              "add",
                "term_code":       f"{tt}_{row['term_code']}",
                "term_name":       row["term_name"],
                "term_type_code":  tt,
                "domain_code":     "DOMAIN_001",
                "library_code":    "LIB_001",
                "parent_term_code": parent,
            }
            for row in rows
        ]
        fname = f"list_terms_{tt}.jsonl"
        _write_jsonl(_OUTPUT / "terms" / fname, entries)
        counts[f"terms/{fname}"] = len(entries)

    # 字典术语合并为一个文件
    dict_entries: list[dict] = []
    for tt, rows in sorted(groups.items()):
        if rows[0]["term_data_type"] != "dict":
            continue
        parent = f"TERM_TYPE_{tt.upper()}"
        for row in rows:
            dict_entries.append({
                "op":              "add",
                "term_code":       f"{tt}_{row['term_code']}",
                "term_name":       row["term_name"],
                "term_type_code":  tt,
                "domain_code":     "DOMAIN_001",
                "library_code":    "LIB_003",
                "parent_term_code": parent,
            })
    _write_jsonl(_OUTPUT / "terms/dict_terms.jsonl", dict_entries)
    counts["terms/dict_terms.jsonl"] = len(dict_entries)

    return counts


def gen_ontology_terms() -> int:
    """生成本体术语（对象/视图/动作/函数）。"""
    print("\n[terms/ontology_terms]")
    type_map = {
        "objects":   "ONTOLOGY_OBJ",
        "views":     "ONTOLOGY_VIEW",
        "actions":   "ONTOLOGY_ACTION",
        "functions": "ONTOLOGY_FUNC",
    }
    entries: list[dict] = []
    for subdir, term_type in type_map.items():
        subdir_path = _ONTO_DIR / subdir
        if not subdir_path.exists():
            continue
        for json_file in sorted(subdir_path.glob("*.json")):
            with open(json_file, encoding="utf-8") as f:
                data = json.load(f)
            tc, tn, desc = _onto_name(data, subdir, json_file.stem)
            entries.append({
                "op":             "add",
                "term_code":      tc,
                "term_name":      tn,
                "term_type_code": term_type,
                "domain_code":    "DOMAIN_001",
                "library_code":   "LIB_001",
                "owl_doc_file":   f"{subdir}/{json_file.name}",
                "desc_summary":   desc,
            })
    _write_jsonl(_OUTPUT / "terms/ontology_terms.jsonl", entries)
    return len(entries)


def gen_relations() -> int:
    """生成术语关系：① term_relation.csv 业务关系；② ontology 本体结构关系。"""
    print("\n[relations]")
    entries: list[dict] = []

    # ── ① 业务关系（term_relation.csv），跳过目标术语不存在的条目 ──────────────
    SKIP = {"REL_003", "REL_004"}
    for r in _read_csv(_TERM_DIR / "term_relation.csv"):
        if r["relation_id"] in SKIP:
            print(f"  skip {r['relation_id']} ({r['relation_name']}) - 目标术语不存在")
            continue
        entries.append({
            "op":                "add",
            "relation_code":     r["relation_id"],
            "source_term_code":  r["source_term_id"],
            "target_term_code":  r["target_term_id"],
            "relation_name":     r["relation_name"],
            "relation_category": "BUSINESS",
            "cardinality":       "1:N",
        })

    # ── ② 本体结构关系（从 ontology JSON 文件提取） ────────────────────────────
    seq = [0]  # 用于生成唯一 relation_code

    def _rel(src: str, tgt: str, name: str) -> dict:
        seq[0] += 1
        return {
            "op":                "add",
            "relation_code":     f"ONTO_REL_{seq[0]:04d}",
            "source_term_code":  src,
            "target_term_code":  tgt,
            "relation_name":     name,
            "relation_category": "ONTOLOGY",
            "cardinality":       "1:N",
        }

    # VIEW → OBJ：视图_包含_对象
    for view_file in sorted((_ONTO_DIR / "views").glob("*.json")):
        view_data = json.loads(view_file.read_text(encoding="utf-8"))
        view_code = view_data.get("view_id", view_file.stem)
        view_name = view_data.get("view_name", view_code)
        for obj_code in view_data.get("object_ids", []):
            entries.append(_rel(view_code, obj_code, f"{view_name}_包含_{obj_code}"))

    # OBJ → ACTION：对象_包含_动作
    # action 的 term_code = 文件 stem（{belong_class}_{action_code}）
    for obj_file in sorted((_ONTO_DIR / "objects").glob("*.json")):
        obj_data  = json.loads(obj_file.read_text(encoding="utf-8"))
        obj_code  = obj_data.get("object_code", obj_file.stem)
        obj_name  = obj_data.get("object_name", obj_code)
        for action_ref in obj_data.get("action_refs", []):
            action_term_code = f"{obj_code}_{action_ref}"
            entries.append(_rel(obj_code, action_term_code, f"{obj_name}_包含_{action_ref}"))

    # ACTION → FUNC：动作_调用_函数
    for act_file in sorted((_ONTO_DIR / "actions").glob("*.json")):
        act_data  = json.loads(act_file.read_text(encoding="utf-8"))
        act_code  = act_file.stem   # term_code 用文件 stem
        act_name  = act_data.get("action_name", act_code)
        for func_ref in act_data.get("function_refs", []):
            entries.append(_rel(act_code, func_ref, f"{act_name}_调用_{func_ref}"))

    _write_jsonl(_OUTPUT / "relations/term_relations.jsonl", entries)
    return len(entries)


def gen_manifest(term_counts: dict[str, int], onto_count: int, rel_count: int) -> None:
    """生成 manifest.json。"""
    print("\n[manifest]")
    steps = [
        {"type": "meta",       "file": "meta/domains.jsonl",       "description": "业务领域定义"},
        {"type": "meta",       "file": "meta/libraries.jsonl",      "description": "知识库定义"},
        {"type": "term_types", "file": "term_types/custom.jsonl",   "description": "自定义术语类型"},
        {"type": "terms",      "file": "terms/concept_terms.jsonl", "description": "概念术语（来自 term.csv 及各类型概念）"},
    ]
    for fname, count in sorted(term_counts.items()):
        steps.append({
            "type":  "terms",
            "file":  fname,
            "description": fname.split("/")[-1].replace(".jsonl", "").replace("_", " "),
            "count": count,
        })
    steps.append({"type": "terms",     "file": "terms/ontology_terms.jsonl",    "description": "本体术语（对象/视图/动作/函数）", "count": onto_count})
    steps.append({"type": "relations", "file": "relations/term_relations.jsonl", "description": "术语关系",                       "count": rel_count})

    _write_json(_OUTPUT / "manifest.json", {
        "version":      "1.0",
        "package_id":   "sales_demo_init_20260318",
        "description":  "销售演示环境知识库初始化导入包（由 _gen_import_package.py 自动生成）",
        "created_at":   "2026-03-18",
        "import_steps": steps,
    })


# ── 主入口 ────────────────────────────────────────────────────────────────────
def main() -> None:
    """执行全量转换。"""
    print("=== 生成导入包 ===")
    _OUTPUT.mkdir(exist_ok=True)

    term_data = _read_csv(_TERM_DIR / "term_data.csv")

    gen_meta()
    gen_term_types(term_data)
    gen_concept_terms(term_data)
    term_counts = gen_list_and_dict_terms(term_data)
    onto_count  = gen_ontology_terms()
    rel_count   = gen_relations()
    gen_manifest(term_counts, onto_count, rel_count)

    print(f"\n[OK] 导入包已生成：{_OUTPUT}")


if __name__ == "__main__":
    main()
