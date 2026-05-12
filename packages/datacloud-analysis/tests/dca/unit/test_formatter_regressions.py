from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_json_markdown_uses_dict_row_values_for_columns_data_shape() -> None:
    """`json` result with {columns, data:[dict]} must render row values, not dict keys."""
    from datacloud_analysis.orchestration.respond.formatter import format_result

    gateway_context = AsyncMock()
    with patch(
        "datacloud_analysis.orchestration.respond.formatter._emit_text",
        new_callable=AsyncMock,
    ) as emit_text:
        await format_result(
            {
                "result_type": "json",
                "data": {
                    "columns": ["a", "b"],
                    "data": [{"a": "1", "b": "2"}],
                },
            },
            gateway_context=gateway_context,
        )

    # _emit_text(text, *, message_id, config) — text is the first positional arg
    markdown_text = emit_text.call_args[0][0]
    row_line = markdown_text.splitlines()[2]
    assert row_line == "| 1 | 2 |"
