"""验证术语提取：主结构 walker + complex_conditions expand_query。

主结构提取不依赖 DB/LLM。
complex_conditions 提取需要 LLM（expand_query）。

Run:
    uv run python packages/datacloud-knowledge/scripts/manual/run_clarify_extract.py
"""

from dotenv import load_dotenv

load_dotenv()


from datacloud_knowledge.intent.clarification.extract import (
    extract_terms_complex_conditions,
    extract_terms_compute,
    extract_terms_query,
)

STRUCTURED_QUERY = {
    "select": ["企业营收", "企业利润"],
    "filters": [{"field": "行业", "op": "eq", "value": "制造业"}],
    "order_by": [{"field": "营收", "direction": "DESC"}],
    "complex_conditions": ["亩产效益后30%的地块"],
}

STRUCTURED_COMPUTE = {
    "dimensions": ["行业类型", "街道"],
    "metrics": [
        {"field": "企业营收", "as": "总营收", "agg": "SUM"},
        {"field": "企业利润", "as": "总利润", "agg": "SUM", "expr": "企业营收 - 企业成本"},
    ],
    "filters": [{"field": "效益等级", "op": "eq", "value": "高效益"}],
    "having": [{"field": "总营收", "op": "gt", "value": 1000}],
    "order_by": [{"field": "总营收", "direction": "DESC"}],
    "complex_conditions": [],
}


def main() -> None:
    # ── 主结构提取（纯本地，无 LLM） ──
    print("=== extract_terms_query ===")
    query_terms = extract_terms_query(STRUCTURED_QUERY)
    for t in query_terms:
        print(f"  {t.ktype:12s} {t.raw_text:12s} search={t.search_enabled}  path={t.path}")

    print("\n=== extract_terms_compute ===")
    compute_terms = extract_terms_compute(STRUCTURED_COMPUTE)
    for t in compute_terms:
        print(f"  {t.ktype:12s} {t.raw_text:12s} search={t.search_enabled}  path={t.path}")

    # ── complex_conditions 提取（需要 LLM: expand_query） ──
    print("\n=== extract_terms_complex_conditions ===")
    print("（调用 expand_query，需要 LLM 环境变量）")
    cc_terms = extract_terms_complex_conditions(STRUCTURED_QUERY["complex_conditions"])
    for t in cc_terms:
        print(f"  {t.ktype:12s} {t.raw_text:12s} search={t.search_enabled}  path={t.path}")

    # ── 汇总 ──
    print(f"\n汇总: query={len(query_terms)}, compute={len(compute_terms)}, cc={len(cc_terms)}")


if __name__ == "__main__":
    main()
