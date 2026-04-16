"""查询跟踪日志：EventTraceLogger 与异常栈输出工具。"""

from __future__ import annotations

import dataclasses
import json
import os
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datacloud_data_sdk.events.bus import EventBus


def log_exception_stack(
    exc: BaseException,
    request_id: str | None = None,
    trace_id: str | None = None,
    path: str | None = None,
) -> None:
    """将异常完整栈输出到 stderr 和 trace 日志文件。

    使用 traceback.format_exception 获取完整栈（与 format_exc 等价，但支持传入异常对象）。
    输出到 sys.stderr 和 path 指定的文件；path=None 时使用
    os.environ.get("DATACLOUD_TRACE_LOG_PATH", "logs/query_trace.log")。
    JSON 行格式：event_type, request_id, trace_id, timestamp(ISO8601), exception, traceback。
    """
    tb_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    exc_str = f"{type(exc).__name__}: {exc}"

    log_path = path or os.environ.get("DATACLOUD_TRACE_LOG_PATH", "logs/query_trace.log")
    record = {
        "event_type": "QueryException",
        "request_id": request_id or "",
        "trace_id": trace_id or "",
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "exception": exc_str,
        "traceback": tb_text,
    }
    line = json.dumps(record, ensure_ascii=False) + "\n"

    print(line, file=sys.stderr, end="")

    try:
        p = Path(log_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass  # 写入失败不中断主流程，设计文档要求


def _build_event_record(event: object) -> dict:
    """将事件序列化为记录格式。"""
    d = dataclasses.asdict(event) if dataclasses.is_dataclass(event) else {}
    request_id = d.pop("request_id", None)
    trace_id = d.pop("trace_id", None)
    payload = d
    return {
        "event_type": type(event).__name__,
        "request_id": request_id,
        "trace_id": trace_id,
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "payload": payload,
    }


class EventTraceLogger:
    """将查询管线事件输出到 stderr 和 trace 日志文件。"""

    def __init__(self, trace_log_path: str, enabled: bool = True) -> None:
        self._trace_log_path = trace_log_path
        self._enabled = enabled

    def register(self, bus: EventBus) -> None:
        """订阅 handlers 中全部 9 种事件类型。"""
        from datacloud_data_sdk.events.events import (
            AggregationCompleted,
            ExecutionTasksReady,
            ObjectViewBuilt,
            PlanRewritten,
            PlanValidated,
            PlanValidationFailed,
            QueryPlanGenerated,
            QueryRequestReceived,
            StepsExecuted,
        )

        all_event_types = [
            QueryRequestReceived,
            ObjectViewBuilt,
            QueryPlanGenerated,
            PlanValidated,
            PlanRewritten,
            ExecutionTasksReady,
            StepsExecuted,
            AggregationCompleted,
            PlanValidationFailed,
        ]

        async def _on_event(event: object) -> None:
            if not self._enabled:
                return
            try:
                record = _build_event_record(event)
                line = json.dumps(record, ensure_ascii=False) + "\n"
                print(line, file=sys.stderr, end="")
                p = Path(self._trace_log_path)
                p.parent.mkdir(parents=True, exist_ok=True)
                with open(p, "a", encoding="utf-8") as f:
                    f.write(line)
            except Exception as exc:
                log_exception_stack(exc, path=self._trace_log_path)

        for event_cls in all_event_types:
            bus.subscribe(event_cls, _on_event)
