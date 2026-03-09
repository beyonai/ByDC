"""聚合器抽象基类。"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any
from datacloud_data_sdk.plan.models import PlanAggregation


class BaseAggregator(ABC):
    @abstractmethod
    async def aggregate(
        self,
        agg: PlanAggregation,
        step_results: dict[str, str],
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        ...
