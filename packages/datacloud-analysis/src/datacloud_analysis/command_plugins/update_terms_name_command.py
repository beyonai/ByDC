"""Handler for async ``updateTermsName`` ext command."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

BatchUpdater = Callable[[tuple[Any, ...]], None]

try:
    from datacloud_knowledge.adapters import create_writer as imported_create_writer
    from datacloud_knowledge.intent import ScoreUpdateRecord as ImportedScoreUpdateRecord
    from datacloud_knowledge.intent import (
        batch_update_scores as imported_batch_update_scores,
    )

    def _do_batch_update(records: tuple[Any, ...]) -> None:
        with imported_create_writer() as writer:
            imported_batch_update_scores(records, writer)

    updater_impl: BatchUpdater | None = _do_batch_update
except ModuleNotFoundError:

    @dataclass(frozen=True)
    class FallbackScoreUpdateRecord:
        """Fallback record type used when datacloud_knowledge is unavailable."""

        name_id: str
        success: bool

    ImportedScoreUpdateRecord = FallbackScoreUpdateRecord
    updater_impl = None

ScoreUpdateRecord = ImportedScoreUpdateRecord

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

    updater = updater_impl
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
