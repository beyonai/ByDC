"""验证统一召回：直接构造 ExtractedTerm 列表，只测 _unified_recall。

不走 extract / expand_query，输入是硬编码的术语。
需要数据库连接（dotenv 加载 DB 环境变量）。

Run:
    uv run python packages/datacloud-knowledge/scripts/manual/run_clarify_recall.py
"""

from dotenv import load_dotenv

load_dotenv()

from datacloud_knowledge.intent.clarification.api import _unified_recall
from datacloud_knowledge.intent.clarification.confirm import format_recall_context
from datacloud_knowledge.intent.clarification.models import ExtractedTerm

# ── 直接构造术语列表（模拟 extract 输出） ────────────────────────────

TERMS: list[ExtractedTerm] = [
    # 主结构
    ExtractedTerm(
        raw_text="企业清单",
        ktype="select",
        path="select.0",
        source="main",
        condition_index=-1,
    ),
    ExtractedTerm(
        raw_text="效能",
        ktype="whereKey",
        path="filters.0.field",
        source="main",
        condition_index=-1,
    ),
    ExtractedTerm(
        raw_text="中效能",
        ktype="whereValue",
        path="filters.0.value",
        source="main",
        condition_index=-1,
    ),
    ExtractedTerm(
        raw_text="低效能",
        ktype="whereValue",
        path="filters.0.value",
        source="main",
        condition_index=-1,
    ),
    # complex_conditions（模拟 expand_query 后的提取结果）
    ExtractedTerm(
        raw_text="亩产效益",
        ktype="select",
        path="complex_conditions.0.select.0",
        source="complex_condition",
        condition_index=0,
    ),
    ExtractedTerm(
        raw_text="地块",
        ktype="groupBy",
        path="complex_conditions.0.where.0.field",
        source="complex_condition",
        condition_index=0,
    ),
]

COMPLEX_CONDITIONS = ["亩产效益后30%的地块"]


def main() -> None:
    print("=== 输入术语 ===")
    for t in TERMS:
        print(f"  {t.source:20s} {t.ktype:12s} {t.raw_text}")

    # ── 统一召回 ──
    print("\n=== 召回结果 ===")
    recall_map = _unified_recall(TERMS)
    for key, candidates in recall_map.items():
        names = [c.get("term_name", "") for c in candidates[:5]]
        print(f"  {key}: {names}")

    # ── 格式化为 recall_context（可直接拷贝到 run_clarify_confirm.py） ──
    print("\n=== recall_context ===")
    ctx = format_recall_context(
        TERMS,
        recall_map,
        complex_conditions=COMPLEX_CONDITIONS,
    )
    print(ctx)


if __name__ == "__main__":
    main()
