"""端到端验证 compute 模式的 analyze_query_clarification。

需要数据库连接：请通过 dotenv 加载相关 DB 环境变量。

Run:
    uv run python packages/datacloud-knowledge/scripts/manual/run_clarify_e2e_compute.py
"""

import json
from dataclasses import asdict

from dotenv import load_dotenv

load_dotenv()

from datacloud_knowledge.intent.clarification.api import analyze_query_clarification
from datacloud_knowledge.intent.types import StreamEvent, StreamEventKind

_last_thinking = ""


def print_event(event: StreamEvent) -> None:
    global _last_thinking
    if event.kind == StreamEventKind.THINKING:
        delta = event.content.removeprefix(_last_thinking)
        if delta:
            print(delta, end="", flush=True)
        _last_thinking = event.content


def main() -> None:
    # 场景：按街道统计企业总营收和总利润，只看制造业，按总营收降序取前10
    query = "各街道制造业企业的总营收和总利润，按总营收从高到低排列，取前10"
    ontology_code = "demo_ontology"
    structured_compute = {
        "dimensions": ["街道"],
        "metrics": [
            {"field": "企业营收", "as": "总营收", "agg": "SUM"},
            {"field": "企业利润", "as": "总利润", "agg": "SUM"},
        ],
        "filters": [{"field": "行业", "op": "eq", "value": "制造业"}],
        "having": [],
        "order_by": [{"field": "总营收", "direction": "DESC"}],
        "limit": 10,
        "complex_conditions": [],
    }

    print("=" * 60)
    print("端到端验证 analyze_query_clarification(mode='compute')")
    print("=" * 60)
    print(f"\nquery: {query}")
    print(f"\nstructured_compute:\n{json.dumps(structured_compute, ensure_ascii=False, indent=2)}")
    print("-" * 60)

    result = analyze_query_clarification(
        query=query,
        ontology_code=ontology_code,
        structured_input=structured_compute,
        mode="compute",
        on_event=print_event,
    )

    print("\n" + "=" * 60)
    print("ClarificationResult:")
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
