"""验证 confirm 模块：直接构造 recall_context，只测 LLM 确认逻辑。

不依赖数据库，不走 extract / recall。
recall_context 内容来自实际召回日志，可按需替换。

Run:
    uv run python packages/datacloud-knowledge/scripts/manual/run_clarify_confirm.py
"""

from dotenv import load_dotenv

load_dotenv()

import json

from datacloud_knowledge.intent.clarification.confirm import llm_confirm_structured
from datacloud_knowledge.intent.types import StreamEvent, StreamEventKind

_last_thinking = ""


def print_event(event: StreamEvent) -> None:
    global _last_thinking
    if event.kind == StreamEventKind.THINKING:
        delta = event.content.removeprefix(_last_thinking)
        if delta:
            print(delta, end="", flush=True)
        _last_thinking = event.content


# ── 输入：从实际召回日志中摘录 ──────────────────────────────────────

QUERY = "找出亩产效益后30%的地块，查询这些地块上的中、低效能的企业清单。"

STRUCTURED_QUERY = {
    "select": ["企业清单"],
    "filters": [
        {"field": "效能", "op": "in", "value": ["中效能", "低效能"]},
    ],
    "order_by": [],
    "complex_conditions": ["亩产效益后30%的地块"],
}

# 直接构造 recall_context，模拟真实召回结果
RECALL_CONTEXT = """\
== 查询值 ==
  企业清单 (select): ['企业数量', '企业等级', '企业全称', '企业详细地址', '企业经营状态']

== 过滤条件（字段） ==
  效能 (whereKey): ['企业经济效益等级（高、中、低）', '企业经营状态', '企业等级', '数据来源', '企业所属物理网格人流活跃等级']

== 过滤条件（值） ==
  中效能 (whereValue): ['中效益企业', '中启能（北京）节能科技有限公司', '中启能科技有限公司', '中洁能控股（集团）有限公司', '中效益管理网格']
  低效能 (whereValue): ['低效益企业', '低效益管理网格', '高效益企业', '绿色低碳场景应用与能源服务', '北京算能科技有限公司']

== complex_conditions 术语 ==
  [0] "亩产效益后30%的地块":
    亩产效益 (select): ['物理网格亩产效益（万元/亩）', '企业总利润（万元）', '企业经济效益等级（高、中、低）', '企业总营收（万元）', '数据来源']
    地块 (groupBy): ['企业详细地址', '企业经营状态', '行业类型', '企业全称', '所属产业环节名称']
"""


def main() -> None:
    print("=" * 60)
    print("验证 confirm 模块（纯 LLM，无 DB 依赖）")
    print("=" * 60)
    print(f"\nquery: {QUERY}")
    print(f"\nstructured_query:\n{json.dumps(STRUCTURED_QUERY, ensure_ascii=False, indent=2)}")
    print(f"\nrecall_context:\n{RECALL_CONTEXT}")
    print("-" * 60)

    confirmed = llm_confirm_structured(
        query=QUERY,
        structured_input=STRUCTURED_QUERY,
        recall_context=RECALL_CONTEXT,
        mode="query",
        on_event=print_event,
    )

    print("\n" + "=" * 60)
    if confirmed is None:
        print("LLM 确认失败")
        return

    print("确认结果:")
    print(json.dumps(confirmed.model_dump(), ensure_ascii=False, indent=2))

    # 关键字段摘要
    print("\n--- 摘要 ---")
    print(f"needs_clarification: {confirmed.needs_clarification}")
    print(f"clarify_items: {len(confirmed.clarify_items)} 项")
    for ci in confirmed.clarify_items:
        print(f"  - {ci.keyword} ({ci.source}): {ci.candidates}")
    print(f"confirmed_conditions: {len(confirmed.confirmed_conditions)} 条")
    for cc in confirmed.confirmed_conditions:
        print(f"  - {cc.original_sentence}")
        for tm in cc.term_mappings:
            status = f"confirmed={tm.confirmed}" if tm.confirmed else f"candidates={tm.candidates}"
            print(f"    {tm.original_term}@[{tm.start}:{tm.end}] → {status}")


if __name__ == "__main__":
    main()
