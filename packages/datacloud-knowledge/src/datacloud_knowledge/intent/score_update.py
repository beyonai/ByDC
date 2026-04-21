"""score 闭环更新 — 算法 E。"""

from __future__ import annotations

import concurrent.futures
import json
import logging
from datetime import UTC, datetime
from importlib import import_module
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

if TYPE_CHECKING:
    from .types import ScoreUpdateRecord

log = logging.getLogger(__name__)

_DECAY_RECENT = 1.0
_DECAY_MODERATE = 0.8
_DECAY_OLD = 0.5
_RECENT_DAYS = 30
_MODERATE_DAYS = 90


def update_scores(
    records: tuple[ScoreUpdateRecord, ...],
    session: Any,
) -> None:
    """Batch update scores for alias records used in this dialog.

    For each record, reads current search_scope from DB, applies
    decay + count update + score recalculation, writes back.

    Args:
        records: Alias records to update (name_id + success flag).
        session: SQLAlchemy Session.
    """
    now = datetime.now(tz=UTC)

    for record in records:
        row = session.execute(
            text("SELECT search_scope FROM term_name WHERE name_id = :name_id"),
            {"name_id": record.name_id},
        ).fetchone()
        if row is None:
            log.debug("Skip score update for missing name_id=%s", record.name_id)
            continue

        search_scope = _parse_search_scope(row[0])
        if search_scope is None:
            log.warning("Skip score update for invalid search_scope name_id=%s", record.name_id)
            continue

        if not search_scope.get("scope_user_id"):
            log.debug("Skip score update for global alias name_id=%s", record.name_id)
            continue

        use_count = _coerce_int(search_scope.get("use_count"))
        confirmed_count = _coerce_int(search_scope.get("confirmed_count"))
        decay = _compute_decay(_coerce_last_used_at(search_scope.get("last_used_at")))

        use_count += 1
        if record.success:
            confirmed_count += 1

        score = _recalculate_score(confirmed_count, use_count, decay)
        search_scope.update(
            {
                "use_count": use_count,
                "confirmed_count": confirmed_count,
                "score": score,
                "last_used_at": now.isoformat(),
            }
        )

        session.execute(
            text(
                "UPDATE term_name "
                "SET search_scope = CAST(:search_scope AS jsonb), updated_time = :now "
                "WHERE name_id = :name_id"
            ),
            {
                "name_id": record.name_id,
                "search_scope": json.dumps(search_scope),
                "now": now,
            },
        )


def _compute_decay(last_used_at: str | None) -> float:
    """Compute step-based time decay factor."""
    if last_used_at is None:
        return _DECAY_RECENT
    try:
        last_dt = datetime.fromisoformat(last_used_at)
    except (ValueError, TypeError):
        return _DECAY_RECENT
    if last_dt.tzinfo is None:
        last_dt = last_dt.replace(tzinfo=UTC)
    days = (datetime.now(tz=UTC) - last_dt).days
    if days <= _RECENT_DAYS:
        return _DECAY_RECENT
    if days <= _MODERATE_DAYS:
        return _DECAY_MODERATE
    return _DECAY_OLD


def _recalculate_score(confirmed_count: int, use_count: int, decay: float) -> float:
    """Recalculate score using pseudocode formula.

    score = confirmed_count / (use_count + 1) * decay_factor
    """
    return confirmed_count / (use_count + 1) * decay


def _parse_search_scope(search_scope_value: Any) -> dict[str, Any] | None:
    """Normalize DB search_scope payload to a dict."""
    if isinstance(search_scope_value, dict):
        return dict(search_scope_value)
    if isinstance(search_scope_value, str):
        try:
            parsed = json.loads(search_scope_value)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, dict):
            return parsed
    return None


def _coerce_int(value: Any) -> int:
    """Convert count-like values to int with a safe fallback."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _coerce_last_used_at(value: Any) -> str | None:
    """Return ISO timestamp string if present."""
    if isinstance(value, str):
        return value
    return None


def update_score(name_id: str, success: bool, session: Any) -> None:
    """Update score for a single alias record.

    Convenience wrapper around update_scores() for single-record use.

    Args:
        name_id: The alias record ID.
        success: Whether the alias was confirmed (True) or rejected (False).
        session: SQLAlchemy Session.
    """
    types_module: Any = import_module(f"{__package__}.types")
    score_update_record = types_module.ScoreUpdateRecord
    update_scores(records=(score_update_record(name_id=name_id, success=success),), session=session)


def update_score_async(name_id: str, success: bool, session: Any) -> None:
    """Asynchronously update score using ThreadPoolExecutor.

    Fire-and-forget: failures are logged, not raised.

    Args:
        name_id: The alias record ID.
        success: Whether the alias was confirmed or rejected.
        session: SQLAlchemy Session.
    """
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    def _task() -> None:
        try:
            update_score(name_id, success, session)
        except Exception:
            log.exception("Async score update failed for name_id=%s", name_id)

    executor.submit(_task)


def batch_update_scores(records: tuple[ScoreUpdateRecord, ...], session: Any) -> None:
    """Batch update scores for multiple alias records.

    Alias for update_scores() with explicit naming for public API.

    Args:
        records: Alias records to update.
        session: SQLAlchemy Session.
    """
    update_scores(records=records, session=session)
