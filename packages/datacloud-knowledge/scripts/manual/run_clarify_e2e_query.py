"""端到端验证 analyze_query_clarification_query。

需要数据库连接：请通过 dotenv 加载相关 DB 环境变量。

Run:
    uv run python packages/datacloud-knowledge/scripts/manual/run_clarify_e2e_query.py
"""

import json
from dataclasses import asdict

from dotenv import load_dotenv

load_dotenv()

from datacloud_knowledge.intent.clarification.api import analyze_query_clarification_query
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
    # 场景：找出亩产效益后30%的地块上的中低效能企业清单
    query = "找出亩产效益后30%的地块，查询这些地块上的中、低效能的企业清单。"
    ontology_code = "demo_ontology"
    structured_query = {
        "select": ["企业清单"],
        "filters": [
            {"field": "效能", "op": "in", "value": ["中效能", "低效能"]},
        ],
        "order_by": [],
        "complex_conditions": ["亩产效益后30%的地块"],
    }

    print("=" * 60)
    print("端到端验证 analyze_query_clarification_query")
    print("=" * 60)
    print(f"\nquery: {query}")
    print(f"\nstructured_query:\n{json.dumps(structured_query, ensure_ascii=False, indent=2)}")
    print("-" * 60)

    result = analyze_query_clarification_query(
        query=query,
        ontology_code=ontology_code,
        structured_query=structured_query,
        on_event=print_event,
    )

    print("\n" + "=" * 60)
    print("ClarificationResult:")
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
