"""端到端验证 query 模式的 analyze_query_clarification。

需要数据库连接：请通过 dotenv 加载相关 DB 环境变量。

Run:
    uv run python packages/datacloud-knowledge/scripts/manual/run_clarify_e2e_query.py
"""

import json
import logging
from dataclasses import asdict

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)-5s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

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
    query = "查询签约成功的商机信息，返回商机名称和签约金额"
    ontology_code = "by_opportunity"
    structured_query = {
        "select": ["opp_name", "contract_amount"],
        "filters": [{"field": "opp_status", "op": "eq", "value": "签约成功"}],
        "complex_conditions": [],
    }
    # structured_query = {'select': ['opp_name', 'contract_amount'], 'filters': [{'field': 'sales_person', 'op': 'eq', 'value': '黄药师'}], 'complex_conditions': []}

    # query= '查询销售用户黄牛逼的商机信息，展示商机名称和签约金额'
    # ontology_code='scene_sales_management'
    # structured_query= {'select': ['opp_name', 'contract_amount'], 'filters': [{'field': 'sales_user_user_name', 'op': 'eq', 'value': '黄牛逼'}], 'complex_conditions': []}

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
