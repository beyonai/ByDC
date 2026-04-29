# ruff: noqa: T201, RUF001, RUF002
"""场景一：正常流程（无中断）。"""

import asyncio
import sys
import uuid

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

from datacloud_analysis.ontology_agent import (
    AnswerEvent,
    ErrorEvent,
    InterruptEvent,
    OntologyAgent,
    OntologyAgentConfig,
    StepEvent,
    ThinkingEvent,
)


async def main() -> None:
    config = OntologyAgentConfig(
        api_key="sk-DRwRYfqi5HpHFbpTjVWRr",
        model="kimi-k2.6",
        base_url="https://api.moonshot.cn/v1",
        resource_path=r"D:\data\code\baiying\byclaw-all\byclaw-data\resource",
        temperature=0.6,
        model_kwargs={"extra_body": {"thinking": {"type": "disabled"}}},
    )
    agent = OntologyAgent(config)

    thread_id = str(uuid.uuid4())

    async for event in agent.ask(
        question=r"""各查询2条项目的数据。

按以下解析，不要做任何推理和改变。
{
  "select": [
    "project_code",
    "project_name",
    "industry",
    "domain",
    "customer_code",
    "project_status",
    "contract_amount",
    "revenue_amount",
    "payment_amount",
    "arrear_amount",
    "plan_online_month",
    "actual_online_month",
    "plan_revenue_month",
    "actual_revenue_month",
    "plan_payment_month",
    "actual_payment_month"
  ],
  "query": "查询2条项目的数据，不要添加任何条件",
  "filters": [],
  "limit": 2,
  "order_by": [],
  "complex_conditions": []
}""",
        object_codes=["by_project"],
        thread_id=thread_id,
    ):
        match event:
            case ThinkingEvent(content=c):
                print(c, end="", flush=True)
            case StepEvent(title=t):
                print(f"\n[{t}]")
            case AnswerEvent(content=a):
                print(f"\n\n=== 答案 ===\n{a}")
            case ErrorEvent(message=m):
                print(f"\n[错误] {m}")
            case InterruptEvent():
                print("\n[意外中断]")


asyncio.run(main())
