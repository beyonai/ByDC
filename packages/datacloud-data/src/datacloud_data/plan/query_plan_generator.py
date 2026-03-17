"""QueryPlanGenerator: LLM 驱动的查询计划生成。"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import asdict
from typing import Any

from datacloud_data.exceptions import (
    CannotAnswerError,
    PlanGenerationError,
    PlanValidationError,
)
from datacloud_data.plan.models import (
    ObjectViewPayload,
    PlanAggregation,
    PlanStep,
    QueryExecutionPlan,
    parse_plan,
)
from datacloud_data.utils.case_utils import camel_to_snake_keys, snake_to_camel_keys








class BasePlanGenerator(ABC):
    @abstractmethod
    async def generate(
        self,
        payload: ObjectViewPayload,
        question: str,
        validation_errors: list[str] | None = None,
        term_loader: Any = None,
    ) -> QueryExecutionPlan:
        ...


class MockPlanGenerator(BasePlanGenerator):
    """Mock 计划生成器，直接返回固定计划，用于测试。"""

    def __init__(self, fixed_plan: dict[str, Any]) -> None:
        self._plan = fixed_plan

    async def generate(
        self,
        payload: ObjectViewPayload,
        question: str,
        validation_errors: list[str] | None = None,
        term_loader: Any = None,
    ) -> QueryExecutionPlan:
        data = camel_to_snake_keys(self._plan)
        return parse_plan(data, question)  # type: ignore[arg-type]


class LangGraphPlanGenerator(BasePlanGenerator):
    """基于 PlanAgent（LangGraph 编排）的查询计划生成器。

    委托 PlanAgent.run() 完成 LLM 调用、Prompt 构造、JSON 解析与校验重试，
    根据返回值抛出 CannotAnswerError / PlanValidationError 或返回 plan。
    """

    def __init__(
        self,
        model: str = "gpt-4o",
        base_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        temperature: float = 0.0,
        max_retries: int = 2,
    ) -> None:
        from datacloud_data.agents import PlanAgent

        self._agent = PlanAgent(
            model=model,
            base_url=base_url,
            api_key=api_key,
            temperature=temperature,
            max_retries=max_retries,
        )

    async def generate(
        self,
        payload: ObjectViewPayload,
        question: str,
        validation_errors: list[str] | None = None,
        term_loader: Any = None,
    ) -> QueryExecutionPlan:
        """调用 PlanAgent.run() 生成并校验计划，根据返回值抛异常或返回 plan。"""
        plan, vr = await self._agent.run(payload, question, term_loader)
        if not plan.can_answer:
            raise CannotAnswerError(plan.clarification)
        if vr and not vr.valid:
            raise PlanValidationError(vr.errors, plan=plan)
        return plan


