from __future__ import annotations

from typing import Any

from datacloud_service.commands.update_terms_name_command import handle_update_terms_name_command


def test_update_terms_name_command_updates_scores(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    def _fake_batch(records: tuple[Any, ...]) -> None:
        captured["records"] = records

    monkeypatch.setattr(
        "datacloud_service.commands.update_terms_name_command.batch_update_scores_with_session",
        _fake_batch,
    )

    handled, payload = handle_update_terms_name_command(
        ext_params={
            "command": "updateTermsName",
            "score_records": [
                {"name_id": "n1", "success": True},
                {"name_id": "n2", "success": False},
            ],
        }
    )

    assert handled is True
    assert payload == {"code": 0, "message": "success", "data": {"updated": 2}}
    assert len(captured["records"]) == 2


def test_update_terms_name_command_silent_mode_returns_no_payload(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        "datacloud_service.commands.update_terms_name_command.batch_update_scores_with_session",
        lambda _records: None,
    )

    handled, payload = handle_update_terms_name_command(
        ext_params={
            "command": "updateTermsName",
            "silent": True,
            "score_records": [{"name_id": "n1", "success": True}],
        }
    )

    assert handled is True
    assert payload is None

