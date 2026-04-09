"""Handler for async ``updateTermsName`` ext command."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from collections.abc import Callable

try:
    from datacloud_knowledge.intent import ScoreUpdateRecord
    from datacloud_knowledge.intent import batch_update_scores_with_session
except ModuleNotFoundError:

    @dataclass(frozen=True)
    class ScoreUpdateRecord:
        """Fallback record type used when datacloud_knowledge is unavailable."""

        name_id: str
        success: bool

    batch_update_scores_with_session: Callable[[tuple[ScoreUpdateRecord, ...]], None] | None = None

logger = logging.getLogger(__name__)


def handle_update_terms_name_command(  # noqa: PLR0911
    *,
    ext_params: dict[str, Any],
) -> tuple[bool, dict[str, Any] | None]:
    """Handle term-name score update command."""
    command = ext_params.get("command")
    if not isinstance(command, str) or command.strip() != "updateTermsName":
        return False, None

    silent = bool(ext_params.get("silent"))
    raw_records = ext_params.get("score_records")
    if not isinstance(raw_records, list):
        message = "score_records must be a list"
        logger.warning("updateTermsName ignored: %s", message)
        if silent:
            return True, None
        return True, {"code": 1, "message": message, "data": {"updated": 0}}

    records = tuple(
        ScoreUpdateRecord(
            name_id=str(record.get("name_id", "")).strip(),
            success=bool(record.get("success")),
        )
        for record in raw_records
        if isinstance(record, dict) and str(record.get("name_id", "")).strip()
    )

    updater = batch_update_scores_with_session
    if updater is None:
        message = "datacloud_knowledge is unavailable"
        logger.warning("updateTermsName ignored: %s", message)
        if silent:
            return True, None
        return True, {"code": 1, "message": message, "data": {"updated": 0}}

    try:
        if records:
            updater(records)
    except Exception as exc:  # noqa: BLE001
        logger.warning("updateTermsName failed: %s", exc)
        if silent:
            return True, None
        return True, {"code": 1, "message": str(exc), "data": {"updated": 0}}

    if silent:
        return True, None
    return True, {"code": 0, "message": "success", "data": {"updated": len(records)}}
