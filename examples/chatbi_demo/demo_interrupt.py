# ruff: noqa: T201, RUF001, RUF002
"""场景二：中断 + 用户确认 + 恢复。"""

import asyncio
import uuid
from collections.abc import AsyncGenerator

from datacloud_analysis.ontology_agent import (
    AnswerEvent,
    ErrorEvent,
    InterruptEvent,
    OntologyAgent,
    OntologyAgentConfig,
    OntologyAgentEvent,
    ParadigmAnswer,
    ParadigmGroupSelection,
    StepEvent,
    ThinkingEvent,
)


async def stream_until_interrupt(
    iterator: AsyncGenerator[OntologyAgentEvent, None],
) -> InterruptEvent | None:
    async for event in iterator:
        match event:
            case ThinkingEvent(content=c):
                print(c, end="", flush=True)
            case StepEvent(title=t):
                print(f"\n[{t}]")
            case AnswerEvent(content=a):
                print(f"\n\n=== 答案 ===\n{a}")
            case ErrorEvent(message=m):
                print(f"\n[错误] {m}")
            case InterruptEvent() as ie:
                return ie
    return None


def mock_user_select(event: InterruptEvent) -> ParadigmAnswer:
    """模拟用户在 UI 选择维度（真实场景由前端完成）。"""
    print(f"\n[需要澄清] {event.prompt}")
    selections = []
    for group in event.paradigm_list or []:
        print(f"  维度「{group.paradigm_name}」→ 自动选第一项：{group.options[0].choice_keyword}")
        selections.append(
            ParadigmGroupSelection(
                paradigm_id=group.paradigm_id,
                paradigm_name=group.paradigm_name,
                chosen_options=group.options[:1],
            )
        )
    return ParadigmAnswer(selections=selections)


async def main() -> None:
    config = OntologyAgentConfig(
        api_key="sk-xxx",
        model="deepseek-v3",
        base_url="https://api.example.com/v1",
        resource_path="/data/byclaw-data/resource",
    )
    agent = OntologyAgent(config)
    view_codes = ["scene_sales"]

    thread_id = str(uuid.uuid4())

    print("问：华东区域的销售额是多少？\n")
    interrupt_event = await stream_until_interrupt(
        agent.ask(
            question="华东区域的销售额是多少？",
            view_codes=view_codes,
            thread_id=thread_id,
            user_code="user_001",
        )
    )
    if interrupt_event is None:
        return

    user_answer = mock_user_select(interrupt_event)

    print("\n[继续执行...]\n")
    await stream_until_interrupt(
        agent.resume(
            thread_id=thread_id,
            user_input=user_answer,
            view_codes=view_codes,
            user_code="user_001",
        )
    )


asyncio.run(main())
