"""聚合器抽象基类。"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any
from datacloud_data.plan.models import PlanAggregation

if TYPE_CHECKING:
    from datacloud_data.executor.step_results import StepResults


class BaseAggregator(ABC):
    @abstractmethod
    async def aggregate(
        self,
        agg: PlanAggregation,
        step_results: "StepResults",
        **kwargs: Any,
    ) -> list[dict[str, Any]]: ...
