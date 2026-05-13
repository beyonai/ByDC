import json

import pytest
from datacloud_data_service.api.mcp_sdk_handler import (
    _build_sdk_envelope_text,
    _McpGatewayContext,
    _parse_bool_header,
    _render_tool_call_text,
    _validate_tool_arguments,
    _wrap_raw_data_as_payload,
)


def test_parse_bool_header_defaults_to_false() -> None:
    assert _parse_bool_header(None) is False
    assert _parse_bool_header("false") is False
    assert _parse_bool_header("0") is False


def test_parse_bool_header_treats_present_value_as_true() -> None:
    assert _parse_bool_header("") is True
    assert _parse_bool_header("true") is True
    assert _parse_bool_header("detail") is True


def test_render_tool_call_text_without_detail_strips_plan() -> None:
    payload = {
        "content": [
            {
                "type": "text",
                "text": _build_sdk_envelope_text(
                    {
                        "records": [{"id": 1}],
                        "meta": {"total": 1},
                        "plan": {"steps": [{"step_id": "s1"}]},
                        "execution_steps": [{"step": "action_executing"}],
                    }
                ),
            }
        ],
        "isError": False,
    }

    rendered = _render_tool_call_text(payload, include_detail=False)

    assert json.loads(rendered) == {
        "records": [{"id": 1}],
        "meta": {"total": 1},
    }


def test_render_tool_call_text_with_detail_keeps_envelope() -> None:
    payload = _wrap_raw_data_as_payload(
        {
            "records": [{"id": 1}],
            "plan": {"steps": [{"step_id": "s1"}]},
        }
    )

    rendered = _render_tool_call_text(payload, include_detail=True)

    assert json.loads(rendered) == {
        "code": 0,
        "message": "success",
        "data": {
            "records": [{"id": 1}],
            "plan": {"steps": [{"step_id": "s1"}]},
        },
    }


def test_validate_tool_arguments_logs_validation_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "datacloud_data_service.api.mcp_sdk_handler._resolve_tool_input_schema",
        lambda *args, **kwargs: {
            "type": "object",
            "properties": {
                "enterprise_level_name": {
                    "type": "string",
                    "enum": [],
                }
            },
            "required": ["enterprise_level_name"],
        },
    )
    log_messages: list[str] = []

    def _fake_exception(message: str, *args: object) -> None:
        log_messages.append(message % args)

    monkeypatch.setattr(
        "datacloud_data_service.api.mcp_sdk_handler.logger.exception",
        _fake_exception,
    )

    result = _validate_tool_arguments(
        "query_scene_enterprise_analysis",
        {"enterprise_level_name": "L1"},
        loader=object(),
    )

    assert result is not None
    assert result[0].text == "输入校验失败：'L1' is not one of []"
    assert log_messages == [
        "call_tool input validation failed: tool=query_scene_enterprise_analysis "
        'arguments={"enterprise_level_name":"L1"}'
    ]


async def test_mcp_gateway_context_sends_log_notifications() -> None:
    class _FakeSession:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        async def send_log_message(
            self,
            level: str,
            data: object,
            logger: str | None = None,
            related_request_id: str | None = None,
        ) -> None:
            self.calls.append(
                {
                    "level": level,
                    "data": data,
                    "logger": logger,
                    "related_request_id": related_request_id,
                }
            )

    session = _FakeSession()
    ctx = _McpGatewayContext(session, "req-1")

    await ctx.emit_state("动作执行", message_id="m1", parent_message_id="root")
    await ctx.emit_chunk("step data", message_id="m1", parent_message_id="root")

    assert len(session.calls) == 2
    assert session.calls[0]["data"] == {
        "event": "tool_call_step",
        "phase": "state",
        "content": "动作执行",
        "message_id": "m1",
        "parent_message_id": "root",
        "event_type": "",
        "content_type": "",
    }
    assert session.calls[1]["data"] == {
        "event": "tool_call_step",
        "phase": "chunk",
        "content": "step data",
        "message_id": "m1",
        "parent_message_id": "root",
        "event_type": "",
        "content_type": "",
    }
