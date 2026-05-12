"""Knowledge tool unit tests."""

from __future__ import annotations

from typing import Any

import pytest

pytest.importorskip("datacloud_analysis.tools.knowledge")

from datacloud_analysis.tools.knowledge import update_term_scores


@pytest.mark.asyncio
async def test_update_term_scores_dispatches_async_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeContext:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        async def call_agent(self, **kwargs: Any) -> dict[str, Any]:
            self.calls.append(kwargs)
            return {"status": "queued"}

    context = _FakeContext()
    monkeypatch.setenv("DATACLOUD_GATEWAY_WORKER_ID", "datacloud")

    await update_term_scores(
        [
            {"name_id": "name-1", "success": True},
            {"name_id": "name-2", "success": False},
            {"name_id": "", "success": True},
        ],
        gateway_context=context,
    )

    assert len(context.calls) == 1
    call = context.calls[0]
    assert call["target_agent_type"] == "datacloud"
    assert call["wait_for_reply"] is False
    assert call["payload"]["ext_params"]["command"] == "updateTermsName"
    assert call["payload"]["ext_params"]["silent"] is True
    assert call["payload"]["ext_params"]["score_records"] == [
        {"name_id": "name-1", "success": True},
        {"name_id": "name-2", "success": False},
    ]
