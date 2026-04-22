"""验证分治确认完整链路：pre_resolve → 编号术语 → LLM 确认 → merge。

Run:
    uv run python packages/datacloud-knowledge/scripts/manual/run_split_confirm_v3.py
"""

from dotenv import load_dotenv

load_dotenv()

import json
import logging
from typing import Any

from datacloud_knowledge.intent.clarification.confirm import (
    CC_CONFIRM_SYSTEM_PROMPT,
    MAIN_CONFIRM_SYSTEM_PROMPT,
    format_cc_confirm_context,
    format_main_confirm_context,
    llm_confirm_cc,
    llm_confirm_main,
)
from datacloud_knowledge.intent.clarification.models import (
    CCConfirmResult,
    CCTermMeta,
    ClarifyItem,
    ConditionTermMapping,
    ConfirmedCondition,
    ConfirmedStructuredQuery,
    ExtractedTerm,
    MainConfirmResult,
    PreResolveResult,
    TermMeta,
)
from datacloud_knowledge.intent.types import StreamEvent, StreamEventKind
from datacloud_knowledge.knowledge_search.types import ResolvedField

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_last_thinking = ""


def print_event(event: StreamEvent) -> None:
    global _last_thinking
    if event.kind == StreamEventKind.THINKING:
        delta = event.content.removeprefix(_last_thinking)
        if delta:
            print(delta, end="", flush=True)
        _last_thinking = event.content


# ── 测试数据 ─────────────────────────────────────────────────────────

STRUCTURED_QUERY: dict[str, Any] = {
    "select": ["企业清单"],
    "filters": [
        {"field": "效能", "op": "in", "value": ["中效能", "低效能"]},
    ],
    "order_by": [],
    "complex_conditions": ["亩产效益后30%的地块"],
}

# 模拟 pre_resolve 结果（按 path:raw_text 复合键入）
PRE_RESOLVE = PreResolveResult(
    confirmed={
        "filters.0.field:效能": ResolvedField(
            term_code="ent_eco_eff_level", term_name="企业经济效益等级（高、中、低）"
        ),
    },
    unresolved_terms=[
        ExtractedTerm(
            raw_text="企业清单",
            ktype="select",
            path="select.0",
            source="main",
            condition_index=-1,
            search_enabled=True,
        ),
        ExtractedTerm(
            raw_text="中效能",
            ktype="whereValue",
            path="filters.0.value.0",
            source="main",
            condition_index=-1,
            search_enabled=True,
        ),
        ExtractedTerm(
            raw_text="低效能",
            ktype="whereValue",
            path="filters.0.value.1",
            source="main",
            condition_index=-1,
            search_enabled=True,
        ),
    ],
    value_enum_map={
        "filters.0.value:中效能": ["中效益企业", "低效益企业", "高效益企业"],
        "filters.0.value:低效能": ["低效益企业", "中效益企业", "高效益企业"],
    },
    provenance={"filters.0.field:效能": "alias_exact"},
)

# 模拟 recall_map（只有 unresolved 术语的召回结果）
RECALL_MAP: dict[str, list[dict[str, Any]]] = {
    "select:企业清单": [
        {"term_name": "企业全称"},
        {"term_name": "企业等级"},
        {"term_name": "企业详细地址"},
        {"term_name": "企业经营状态"},
        {"term_name": "企业数量"},
    ],
    "whereValue:中效能": [
        {"term_name": "中效益企业"},
        {"term_name": "中启能（北京）节能科技有限公司"},
    ],
    "whereValue:低效能": [
        {"term_name": "低效益企业"},
        {"term_name": "低效益管理网格"},
    ],
    "select:亩产效益": [
        {"term_name": "物理网格亩产效益（万元/亩）"},
        {"term_name": "企业总利润（万元）"},
        {"term_name": "企业经济效益等级（高、中、低）"},
        {"term_name": "企业总营收（万元）"},
    ],
    "groupBy:地块": [
        {"term_name": "企业详细地址"},
        {"term_name": "企业经营状态"},
        {"term_name": "行业类型"},
        {"term_name": "企业全称"},
        {"term_name": "所属产业环节名称"},
    ],
}

# 模拟主结构术语（含 whereKey）
MAIN_TERMS = [
    ExtractedTerm(
        raw_text="企业清单", ktype="select", path="select.0",
        source="main", condition_index=-1, search_enabled=True,
    ),
    ExtractedTerm(
        raw_text="效能", ktype="whereKey", path="filters.0.field",
        source="main", condition_index=-1, search_enabled=True,
    ),
    ExtractedTerm(
        raw_text="中效能", ktype="whereValue", path="filters.0.value.0",
        source="main", condition_index=-1, search_enabled=True,
    ),
    ExtractedTerm(
        raw_text="低效能", ktype="whereValue", path="filters.0.value.1",
        source="main", condition_index=-1, search_enabled=True,
    ),
]

CC_TERMS = [
    ExtractedTerm(
        raw_text="亩产效益", ktype="select", path="complex_conditions.0",
        source="complex_condition", condition_index=0, search_enabled=True,
    ),
    ExtractedTerm(
        raw_text="地块", ktype="groupBy", path="complex_conditions.0",
        source="complex_condition", condition_index=0, search_enabled=True,
    ),
]


def main() -> None:
    global _last_thinking

    # ── Part 1: 主结构确认 ──
    print("=" * 60)
    print("Part 1: 主结构确认（编号术语模式）")
    print("=" * 60)

    # 构建 pre_resolved_input
    pre_resolved_input: dict[str, Any] = {
        "select": ["企业清单"],
        "filters": [
            {
                "field": "企业经济效益等级（高、中、低）",
                "op": "in",
                "value": ["中效能", "低效能"],
            },
        ],
        "order_by": [],
    }

    main_context, term_registry = format_main_confirm_context(
        pre_resolved_input, MAIN_TERMS, RECALL_MAP, PRE_RESOLVE, mode="query",
    )

    print("\n--- LLM 输入上下文 ---")
    print(main_context)
    print("\n--- term_registry ---")
    for tid, meta in term_registry.items():
        print(f"  #{tid}: {meta.raw_text} ({meta.ktype}) → path={meta.path}")

    print("\n--- LLM 调用 ---")
    _last_thinking = ""
    main_result = llm_confirm_main(context=main_context, on_event=print_event)
    if main_result:
        print(f"\n\n--- MainConfirmResult ---")
        print(json.dumps(main_result.model_dump(), ensure_ascii=False, indent=2))
    else:
        print("\n  ❌ 主结构确认失败")

    # ── Part 2: cc[0] 确认 ──
    print("\n" + "=" * 60)
    print("Part 2: cc[0] 确认（编号术语模式）")
    print("=" * 60)

    cc_context, cc_registry = format_cc_confirm_context(
        CC_TERMS, RECALL_MAP, "亩产效益后30%的地块", 0,
    )

    print("\n--- LLM 输入上下文 ---")
    print(cc_context)
    print("\n--- cc_term_registry ---")
    for tid, meta in cc_registry.items():
        print(f"  #{tid}: {meta.raw_text} ({meta.ktype}) start={meta.start} end={meta.end}")

    print("\n--- LLM 调用 ---")
    _last_thinking = ""
    cc_result = llm_confirm_cc(context=cc_context, on_event=print_event)
    if cc_result:
        print(f"\n\n--- CCConfirmResult ---")
        print(json.dumps(cc_result.model_dump(), ensure_ascii=False, indent=2))
    else:
        print("\n  ❌ cc 确认失败")

    # ── Part 3: 验证 merge ──
    print("\n" + "=" * 60)
    print("Part 3: Merge 验证")
    print("=" * 60)

    if main_result and cc_result:
        from datacloud_knowledge.intent.clarification.api import _merge_to_confirmed_query

        confirmed = _merge_to_confirmed_query(
            PRE_RESOLVE,
            main_result,
            [(cc_result, cc_registry)],
            term_registry,
            STRUCTURED_QUERY,
            MAIN_TERMS,
        )
        print(json.dumps(confirmed.model_dump(), ensure_ascii=False, indent=2))
        print(f"\nneeds_clarification: {confirmed.needs_clarification}")
        print(f"clarify_items: {len(confirmed.clarify_items)}")
        print(f"confirmed_conditions: {len(confirmed.confirmed_conditions)}")
    else:
        print("  跳过 merge（LLM 调用失败）")


if __name__ == "__main__":
    main()
