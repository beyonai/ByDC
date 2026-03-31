"""Built-in skill: time_series — resample and compute period-over-period delta."""

from __future__ import annotations

from typing import Any

SKILL_META = {
    "name": "time_series",
    "description": "对时序 DataFrame 按指定周期重采样，并计算环比/同比增量。",
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
    """Resample a time-series column and optionally add period-over-period change.

    Args:
        df:        pandas DataFrame with a datetime column.
        date_col:  Name of the datetime column.
        value_col: Column to resample.
        freq:      Resample frequency (pandas offset alias, e.g. 'ME', 'W', 'QE').
        method:    Aggregation applied after resampling.
        add_delta: If True, append a ``{value_col}_delta`` column.

    Returns:
        Resampled DataFrame.
    """
    import pandas as pd  # noqa: PLC0415

    _df = df.copy()
    _df[date_col] = pd.to_datetime(_df[date_col])
    _df = _df.set_index(date_col)
    result = _df[[value_col]].resample(freq).agg(method).reset_index()
    if add_delta:
        result[f"{value_col}_delta"] = result[value_col].diff()
    return result
