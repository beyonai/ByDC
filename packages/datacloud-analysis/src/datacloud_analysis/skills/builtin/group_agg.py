"""Built-in skill: group_agg."""

from __future__ import annotations

from typing import Any

SKILL_META = {
    "name": "group_agg",
    "description": "Group-by aggregation helper supporting sum/mean/count and similar methods.",
    "version": "1.0.0",
    "author": "system",
    "risk_level": "low",
    "allowlist_tags": [],
    "blocklist_tags": [],
}


def run(df: Any, group_by: list[str], agg_col: str, method: str = "sum") -> Any:
    """Group by columns and aggregate one target column."""
    return df.groupby(group_by)[agg_col].agg(method).reset_index()

