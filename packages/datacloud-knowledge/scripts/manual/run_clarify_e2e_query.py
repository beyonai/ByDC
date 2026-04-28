"""端到端验证 query 模式的 analyze_query_clarification。

需要数据库连接：请通过 dotenv 加载相关 DB 环境变量。

Run:
    uv run python packages/datacloud-knowledge/scripts/manual/run_clarify_e2e_query.py
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
    # 场景：找出亩产效益后30%的地块上的中低效能企业清单
    query = "查询物理网格数据，包含网格编码、网格名称、贡献率三个字段，条件是贡献率大于100，返回10条数据"
    ontology_code = "scene_grid_analysis"
    structured_query = {
        "select": ["phy_grid_id", "phy_grid_name", "贡献率"],
        "limit": 10,
        "complex_conditions": ["贡献率大于100"],
    }

    print("=" * 60)
    print("端到端验证 analyze_query_clarification(mode='query')")
    print("=" * 60)
    print(f"\nquery: {query}")
    print(f"\nstructured_query:\n{json.dumps(structured_query, ensure_ascii=False, indent=2)}")
    print("-" * 60)

    result = analyze_query_clarification(
        query=query,
        ontology_code=ontology_code,
        structured_input=structured_query,
        mode="query",
        on_event=print_event,
    )

    print("\n" + "=" * 60)
    print("ClarificationResult:")
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
