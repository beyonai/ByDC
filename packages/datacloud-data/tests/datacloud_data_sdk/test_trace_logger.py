"""Tests for trace_logger.log_exception_stack and EventTraceLogger."""

import asyncio
import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from datacloud_data_sdk.events.trace_logger import log_exception_stack


def test_log_exception_stack_outputs_to_stderr_and_file(tmp_path, capfd) -> None:
    """触发 ValueError，调用 log_exception_stack，断言 stderr 和文件输出正确。"""
    try:
        raise ValueError("test error message")
    except ValueError as e:
        log_exception_stack(e, request_id="rid1", trace_id="tid1", path=str(tmp_path / "trace.log"))

    captured = capfd.readouterr()
    stderr = captured.err

    # stderr 含 QueryException 或 ValueError
    assert "QueryException" in stderr or "ValueError" in stderr

    # 文件存在
    trace_file = tmp_path / "trace.log"
    assert trace_file.exists()

    # JSON 行含 event_type, request_id, trace_id, exception, traceback
    content = trace_file.read_text()
    lines = [line for line in content.strip().split("\n") if line]
    assert len(lines) >= 1
    record = json.loads(lines[-1])
    assert record.get("event_type") == "QueryException"
    assert record.get("request_id") == "rid1"
    assert record.get("trace_id") == "tid1"
    assert "exception" in record
    assert "traceback" in record
    assert "ValueError" in record["exception"]


def test_event_trace_logger_outputs_event_to_stderr_and_file(tmp_path) -> None:
    """EventTraceLogger 将事件输出到 stderr 和文件。"""
    from datacloud_data_sdk.events.bus import EventBus
    from datacloud_data_sdk.events.events import QueryRequestReceived
    from datacloud_data_sdk.events.trace_logger import EventTraceLogger

    log_path = str(tmp_path / "trace.log")
    logger = EventTraceLogger(trace_log_path=log_path, enabled=True)
    bus = EventBus()
    logger.register(bus)

    event = QueryRequestReceived(request_id="r1", trace_id="t1", question="q", object_ids=["o1"])
    with patch("sys.stderr", new_callable=io.StringIO):
        asyncio.run(bus.publish(event))

    assert Path(log_path).exists()
    p = Path(log_path)
    lines = p.read_text().strip().split("\n")
    assert len(lines) >= 1
    obj = json.loads(lines[0])
    assert obj["event_type"] == "QueryRequestReceived"
    assert obj["request_id"] == "r1"
