"""DirectAggregator: 直接返回 final step 的 CSV 结果。"""
from __future__ import annotations
import csv
from pathlib import Path
from typing import Any
from datacloud_data_sdk.aggregator.base import BaseAggregator
from datacloud_data_sdk.plan.models import PlanAggregation


class DirectAggregator(BaseAggregator):
    async def aggregate(
        self,
        agg: PlanAggregation,
        step_results: dict[str, str],
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        if not agg.final_step_id:
            return []
        csv_path = step_results.get(agg.final_step_id, "")
        if not csv_path or not Path(csv_path).exists():
            return []
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            records = list(reader)
        if agg.columns:
            col_names = {c["name"] for c in agg.columns}
            records = [{k: v for k, v in r.items() if k in col_names} for r in records]
        return records
