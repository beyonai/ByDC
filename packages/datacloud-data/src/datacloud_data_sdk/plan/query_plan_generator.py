"""
查询计划生成器模块

本模块提供基于 LLM 的查询计划生成能力，将自然语言问题转换为可执行的查询计划。

核心组件：
- BasePlanGenerator: 计划生成器抽象基类
- MockPlanGenerator: Mock 生成器，用于测试
- LangGraphPlanGenerator: 基于 LangGraph 的 LLM 计划生成器

使用示例：
    generator = LangGraphPlanGenerator(
        model="gpt-4o",
        api_key="your-api-key"
    )
    plan = await generator.generate(payload, "查询所有活跃用户")
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import asdict
from typing import Any

from datacloud_data_sdk.exceptions import (
    CannotAnswerError,
    PlanGenerationError,
    PlanValidationError,
)
from datacloud_data_sdk.plan.models import (
    ObjectViewPayload,
    PlanAggregation,
    PlanStep,
    QueryExecutionPlan,
    parse_plan,
)
from datacloud_data_sdk.utils.case_utils import camel_to_snake_keys, snake_to_camel_keys


class BasePlanGenerator(ABC):
    """
    计划生成器抽象基类

    定义了所有计划生成器必须实现的接口。
    """

    @abstractmethod
    async def generate(
        self,
        payload: ObjectViewPayload,
        question: str,
        validation_errors: list[str] | None = None,
        term_loader: Any = None,
    ) -> QueryExecutionPlan:
        """
        生成查询执行计划

        Args:
            payload: 对象视图载荷
            question: 自然语言问题
            validation_errors: 验证错误列表（用于重试）
            term_loader: 术语加载器

        Returns:
            QueryExecutionPlan: 生成的执行计划
        """
        ...


class MockPlanGenerator(BasePlanGenerator):
    """
    Mock 计划生成器

    直接返回固定计划，用于测试和开发环境。

    Example:
        generator = MockPlanGenerator({"steps": [...], "aggregation": {...}})
        plan = await generator.generate(payload, "test question")
    """

    def __init__(self, fixed_plan: dict[str, Any]) -> None:
        """
        初始化 Mock 生成器

        Args:
            fixed_plan: 固定的计划数据
        """
        self._plan = fixed_plan

    async def generate(
        self,
        payload: ObjectViewPayload,
        question: str,
        validation_errors: list[str] | None = None,
        term_loader: Any = None,
    ) -> QueryExecutionPlan:
        """
        返回固定计划

        Args:
            payload: 对象视图载荷（忽略）
            question: 问题（忽略）
            validation_errors: 验证错误（忽略）
            term_loader: 术语加载器（忽略）

        Returns:
            QueryExecutionPlan: 固定的执行计划
        """
        data = camel_to_snake_keys(self._plan)
        return parse_plan(data, question)


class LangGraphPlanGenerator(BasePlanGenerator):
    """
    基于 LangGraph 的查询计划生成器

    使用 PlanAgent（LangGraph 编排）完成 LLM 调用、Prompt 构造、
    JSON 解析与校验重试。根据返回值抛出相应异常或返回计划。

    Attributes:
        _agent: PlanAgent 实例

    Example:
        generator = LangGraphPlanGenerator(
            model="gpt-4o",
            api_key="your-api-key",
            temperature=0.0
        )
        plan = await generator.generate(payload, "查询销售额前10的产品")
    """

    def __init__(
        self,
        model: str = "gpt-4o",
        base_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        temperature: float = 0.0,
        max_retries: int = 2,
    ) -> None:
        """
        初始化 LangGraph 计划生成器

        Args:
            model: LLM 模型名称
            base_url: API 基础 URL
            api_key: API 密钥
            temperature: 生成温度
            max_retries: 最大重试次数
        """
        from datacloud_data_sdk.agents import PlanAgent

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
        """
        调用 PlanAgent 生成并校验计划

        执行流程：
        1. 调用 PlanAgent.run() 生成计划
        2. 检查是否可回答，否则抛出 CannotAnswerError
        3. 检查验证结果，失败则抛出 PlanValidationError

        Args:
            payload: 对象视图载荷
            question: 自然语言问题
            validation_errors: 验证错误列表（用于重试）
            term_loader: 术语加载器

        Returns:
            QueryExecutionPlan: 生成的执行计划

        Raises:
            CannotAnswerError: 无法回答问题时抛出
            PlanValidationError: 计划验证失败时抛出
        """
        plan, vr = await self._agent.run(payload, question, term_loader)
        if not plan.can_answer:
            raise CannotAnswerError(plan.clarification)
        if vr and not vr.valid:
            raise PlanValidationError(vr.errors, plan=plan)
        return plan
