# ruff: noqa: T201, RUF002, RUF003, E402
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
        api_key="sk-DRwRYfqi5HpHFbpTjVWRrBRck1nLrwkaGvf4ywv49lFAgWRH",
        model="kimi-k2.6",
        base_url="https://api.moonshot.cn/v1",
        resource_path=r"D:\data\code\baiying\byclaw-all\byclaw-data\resource",
        temperature=0.6,
        model_kwargs={"extra_body": {"thinking": {"type": "disabled"}}},
        # HTTP_SQL 后端服务地址；非空时强制走 HttpSqlConnector，
        # 取代历史的 DATACLOUD_SQL_SERVICE_URL 环境变量。
        sql_execute_url="http://172.21.72.156:8570/knowledgeService/callDomainModel/executeSql",
    )
    agent = OntologyAgent(config)

    thread_id = str(uuid.uuid4())

    # 真实 cookie（与本地 byaiClient 后端会话对齐）。生产环境应从安全存储中读取，
    # 此处仅为 demo 直接复用 Postman / curl 调试时的 cookie 头。
    real_cookie = (
        "collect_session_id=1775140228600wynpaFbCipC3Jakj; "
        "lang=EN_US; "
        "_ga=GA1.1.1531564186.1775145663; "
        "_clck=lyfq6n%5E2%5Eg5k%5E0%5E2283; "
        "nh=172.21.72.156:9669; "
        "nu=root; "
        "_ga_8NW26JNFDM=GS2.1.s1777442263$o11$g0$t1777442271$j52$l0$h0; "
        "SESSION=638b8ed1-c81a-4fb8-baef-28d0b82b131e; "
        "td=-18; "
        "uc=admin"
    )

    async for event in agent.ask(
        # 最简自然语言查询：单一对象 + 限制条数，不带任何过滤/排序/聚合
        question="查询前3条客户清单数据",
        object_codes=["by_customer"],
        thread_id=thread_id,
        # extras 透传请求级扩展字段（chatbi 关注的 cookie 在此传入，
        # 由 HttpSqlConnector._build_headers 写入下游 SQL 服务请求头）
        extras={"cookie": real_cookie},
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
