"""验证澄清召回阶段的新分层 scope recall 流程。

该脚本不走 LLM 确认，只手动构造 ExtractedTerm，模拟
``analyze_query_clarification`` 中的：

1. 主结构字段预解析；
2. complex_conditions 字段预解析；
3. 根据已确认字段推断 object scope layer；
4. 对未解析术语执行 `_unified_recall(..., scope_layers=...)`。

Run:
    uv run python packages/datacloud-knowledge/scripts/manual/run_clarify_recall.py
"""

from dotenv import load_dotenv

load_dotenv()

from datacloud_knowledge.intent.clarification.api import (
    _build_scope_recall_layers,
    _pre_resolve_terms,
    _unified_recall,
)
from datacloud_knowledge.intent.clarification.confirm import format_recall_context
from datacloud_knowledge.intent.clarification.models import ExtractedTerm

ONTOLOGY_CODE = "scene_grid_analysis"
COMPLEX_CONDITIONS = ["贡献率大于100"]

MAIN_TERMS: list[ExtractedTerm] = [
    ExtractedTerm(
        raw_text="phy_grid_id",
        ktype="select",
        path="select.0",
        source="main",
        condition_index=-1,
        vector_only=True,
    ),
    ExtractedTerm(
        raw_text="phy_grid_name",
        ktype="select",
        path="select.1",
        source="main",
        condition_index=-1,
        vector_only=True,
    ),
    ExtractedTerm(
        raw_text="贡献率",
        ktype="select",
        path="select.2",
        source="main",
        condition_index=-1,
    ),
]

CC_TERMS: list[ExtractedTerm] = [
    ExtractedTerm(
        raw_text="贡献率",
        ktype="select",
        path="complex_conditions.0.select.0",
        source="complex_condition",
        condition_index=0,
    ),
    ExtractedTerm(
        raw_text="贡献率",
        ktype="whereKey",
        path="complex_conditions.0.where.0.field",
        source="complex_condition",
        condition_index=0,
    ),
]


def _print_terms(title: str, terms: list[ExtractedTerm]) -> None:
    print(f"\n=== {title} ===")
    for term in terms:
        print(f"  {term.source:20s} {term.ktype:12s} {term.raw_text}")


def _print_pre_resolve(title: str, terms: list[ExtractedTerm]) -> None:
    pre = _pre_resolve_terms(terms, scope_code=ONTOLOGY_CODE)
    print(f"\n=== {title} ===")
    print(f"confirmed={len(pre.confirmed)} unresolved={len(pre.unresolved_terms)}")
    for key, resolved in pre.confirmed.items():
        print(f"  {key}: {resolved.term_code} -> {resolved.term_name}")


def main() -> None:
    all_terms = MAIN_TERMS + CC_TERMS
    _print_terms("输入术语", all_terms)

    pre = _pre_resolve_terms(MAIN_TERMS, scope_code=ONTOLOGY_CODE)
    cc_pre = _pre_resolve_terms(CC_TERMS, scope_code=ONTOLOGY_CODE)
    _print_pre_resolve("主结构预解析", MAIN_TERMS)
    _print_pre_resolve("复杂条件预解析", CC_TERMS)

    inferred_layers = _build_scope_recall_layers(ONTOLOGY_CODE, pre, cc_pre)
    scope_layers = inferred_layers if len(inferred_layers) > 1 else None
    print("\n=== 推断 scope layers ===")
    for layer in inferred_layers:
        print(f"  {layer.label or 'scope'}: scope={layer.scope_code} weight={layer.weight:.2f}")
    print(f"  layered_enabled={scope_layers is not None}")

    recall_terms = list(pre.unresolved_terms) + list(cc_pre.unresolved_terms)
    print("\n=== 召回输入（仅 unresolved） ===")
    for term in recall_terms:
        print(f"  {term.ktype:12s} {term.raw_text}")

    recall_map = _unified_recall(
        recall_terms,
        scope_code=ONTOLOGY_CODE,
        scope_layers=scope_layers,
    )

    print("\n=== 召回结果 ===")
    for key, candidates in recall_map.items():
        names = [str(candidate.get("term_name", "")) for candidate in candidates[:5]]
        print(f"  {key}: {names}")

    print("\n=== recall_context ===")
    ctx = format_recall_context(
        recall_terms,
        recall_map,
        complex_conditions=COMPLEX_CONDITIONS,
    )
    print(ctx)


if __name__ == "__main__":
    main()
