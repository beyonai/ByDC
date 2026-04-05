"""Built-in skill: group_agg — group-by aggregation helper."""

from __future__ import annotations

from typing import Any

SKILL_META = {
    "name": "group_agg",
    "description": "按指定维度分组聚合，支持 sum / mean / count / ratio 等聚合方法。",
    "version": "1.0.0",
    "author": "system",
    "risk_level": "low",
    "allowlist_tags": [],
    "blocklist_tags": [],
}


def run(df: Any, group_by: list[str], agg_col: str, method: str = "sum") -> Any:
    """Group a DataFrame and aggregate one column.

    Args:
        df:       pandas DataFrame.
        group_by: Columns to group by.
        agg_col:  Column to aggregate.
        method:   Aggregation method (sum / mean / count / …).

    Returns:
        Aggregated DataFrame.
    """
    return df.groupby(group_by)[agg_col].agg(method).reset_index()
