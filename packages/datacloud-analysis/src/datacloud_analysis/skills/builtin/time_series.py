"""Built-in skill: time_series."""

from __future__ import annotations

from typing import Any

SKILL_META = {
    "name": "time_series",
    "description": "Resample time-series data and optionally compute period-over-period delta.",
    "version": "1.0.0",
    "author": "system",
    "risk_level": "low",
    "allowlist_tags": [],
    "blocklist_tags": [],
}


def run(
    df: Any,
    date_col: str,
    value_col: str,
    freq: str = "ME",
    method: str = "sum",
    add_delta: bool = True,
) -> Any:
    """Resample by period and compute value delta if requested."""
    import pandas as pd  # noqa: PLC0415

    frame = df.copy()
    frame[date_col] = pd.to_datetime(frame[date_col])
    frame = frame.set_index(date_col)
    result = frame[[value_col]].resample(freq).agg(method).reset_index()
    if add_delta:
        result[f"{value_col}_delta"] = result[value_col].diff()
    return result

