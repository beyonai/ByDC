# 查询跟踪输出（控制台 + 日志文件）实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将查询管线的完整事件流输出到控制台和日志文件，异常发生时输出栈信息到控制台和同一日志文件。

**Architecture:** 新增 EventTraceLogger 直接订阅 EventBus 的查询事件，序列化为 JSON 行后写入控制台和文件；新增 log_exception_stack 工具函数，在 View.query、Object.query、UnifiedQuery、EventTraceLogger 的异常路径中调用。

**Tech Stack:** Python, dataclasses, EventBus, pydantic-settings

**参考设计:** `docs/plans/2026-03-09-query-trace-console-and-file-design.md`

---

## Task 1: 配置项 trace_log_path、trace_enabled

**Files:**
- Modify: `datacloud-data/src/datacloud_data_service/config.py`

**Step 1: 在 Settings 中增加字段**

```python
trace_log_path: str = "logs/query_trace.log"  # 环境变量 DC_TRACE_LOG_PATH
trace_enabled: bool = True                     # 环境变量 DC_TRACE_ENABLED
```

**Step 2: 验证**

Run: `python -c "from datacloud_data_service.config import get_settings; s=get_settings(); print(s.trace_log_path, s.trace_enabled)"`
Expected: 输出 `logs/query_trace.log True`

---

## Task 2: log_exception_stack 工具函数

**Files:**
- Create: `datacloud-data/src/datacloud_data/events/trace_logger.py`
- Test: `datacloud-data/tests/datacloud_data/test_trace_logger.py`

**Step 1: 编写失败测试**

```python
"""EventTraceLogger 与 log_exception_stack 测试。"""
import io
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


def test_log_exception_stack_outputs_to_stderr_and_file(tmp_path):
    """log_exception_stack 输出到 stderr 和文件。"""
    from datacloud_data_sdk.events.trace_logger import log_exception_stack

    log_path = tmp_path / "trace.log"
    try:
        raise ValueError("test error")
    except ValueError as e:
        with patch("sys.stderr", new_callable=io.StringIO) as stderr:
            log_exception_stack(e, request_id="rid1", trace_id="tid1", path=str(log_path))

    assert "QueryException" in stderr.getvalue() or "ValueError" in stderr.getvalue()
    assert log_path.exists()
    lines = log_path.read_text().strip().split("\n")
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["event_type"] == "QueryException"
    assert obj["request_id"] == "rid1"
    assert obj["trace_id"] == "tid1"
    assert "ValueError" in obj["exception"]
    assert "traceback" in obj
```

**Step 2: 运行测试确认失败**

Run: `pytest datacloud-data/tests/datacloud_data/test_trace_logger.py::test_log_exception_stack_outputs_to_stderr_and_file -v`
Expected: FAIL (ModuleNotFoundError 或 ImportError)

**Step 3: 实现 log_exception_stack**

在 `trace_logger.py` 中：

```python
"""查询跟踪日志：EventTraceLogger 与 log_exception_stack。"""
from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path


def log_exception_stack(
    exc: BaseException,
    request_id: str | None = None,
    trace_id: str | None = None,
    path: str | None = None,
) -> None:
    """将异常栈输出到 stderr 和日志文件。path=None 时从 DC_TRACE_LOG_PATH 读取。"""
    tb_text = traceback.format_exc()
    exc_str = f"{type(exc).__name__}: {exc}"
    payload = {
        "event_type": "QueryException",
        "request_id": request_id or "",
        "trace_id": trace_id or "",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "exception": exc_str,
        "traceback": tb_text,
    }
    line = json.dumps(payload, ensure_ascii=False) + "\n"
    try:
        print(line.strip(), file=sys.stderr)
    except Exception:
        pass
    log_path = path or os.environ.get("DC_TRACE_LOG_PATH", "logs/query_trace.log")
    try:
        p = Path(log_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.open("a", encoding="utf-8").write(line)
    except Exception:
        pass
```

**Step 4: 运行测试确认通过**

Run: `pytest datacloud-data/tests/datacloud_data/test_trace_logger.py::test_log_exception_stack_outputs_to_stderr_and_file -v`
Expected: PASS

---

## Task 3: EventTraceLogger 类与事件序列化

**Files:**
- Modify: `datacloud-data/src/datacloud_data/events/trace_logger.py`
- Test: `datacloud-data/tests/datacloud_data/test_trace_logger.py`

**Step 1: 编写 EventTraceLogger 测试**

```python
def test_event_trace_logger_outputs_event_to_stderr_and_file(tmp_path):
    """EventTraceLogger 将事件输出到 stderr 和文件。"""
    from datacloud_data_sdk.events.bus import EventBus
    from datacloud_data_sdk.events.events import QueryRequestReceived
    from datacloud_data_sdk.events.trace_logger import EventTraceLogger

    log_path = str(tmp_path / "trace.log")
    logger = EventTraceLogger(trace_log_path=log_path, enabled=True)
    bus = EventBus()
    logger.register(bus)

    event = QueryRequestReceived(
        request_id="r1", trace_id="t1", question="q", object_ids=["o1"]
    )
    import asyncio
    with patch("sys.stderr", new_callable=io.StringIO) as stderr:
        asyncio.run(bus.publish(event))

    assert Path(log_path).exists()
    p = Path(log_path)
    assert p.exists()
    lines = p.read_text().strip().split("\n")
    assert len(lines) >= 1
    obj = json.loads(lines[0])
    assert obj["event_type"] == "QueryRequestReceived"
    assert obj["request_id"] == "r1"
```

**Step 2: 实现 EventTraceLogger**

在 `trace_logger.py` 中增加 EventTraceLogger 类，参考 handlers.py 的 all_event_types 订阅所有事件类型。序列化时使用 `dataclasses.asdict` 或手动提取 request_id、trace_id、timestamp、payload。输出到 stderr 和文件。内部异常时调用 `log_exception_stack`。

**Step 3: 运行测试**

Run: `pytest datacloud-data/tests/datacloud_data/test_trace_logger.py -v`

---

## Task 4: 在 routes.py 中集成 EventTraceLogger

**Files:**
- Modify: `datacloud-data/src/datacloud_data_service/api/routes.py`

**Step 1: 在 create_app 的 _lifespan 中，register_query_handlers 之后**

```python
from datacloud_data_sdk.events.trace_logger import EventTraceLogger

# 在 register_query_handlers(bus, tracing=tracing) 之后
if settings.trace_enabled:
    trace_logger = EventTraceLogger(
        trace_log_path=settings.trace_log_path,
        enabled=True,
    )
    trace_logger.register(bus)
```

**Step 2: 确认 Settings 有 trace_log_path、trace_enabled**

若 Task 1 未完成，需先完成。

**Step 3: 验证**

启动服务，发查询请求，检查控制台和 `logs/query_trace.log` 是否有 JSON 行输出。

---

## Task 5: View.query 异常时调用 log_exception_stack

**Files:**
- Modify: `datacloud-data/src/datacloud_data/view.py`

**Step 1: 在 query 方法中增加异常捕获**

当前结构为 `try: ... return ... finally: csv_manager.cleanup(request_id)`。需在 try 与 finally 之间增加 except：

```python
try:
    # 现有 try 块内容
    ...
    return {...}
except Exception as exc:
    from datacloud_data_sdk.events.trace_logger import log_exception_stack
    log_exception_stack(exc, request_id=request_id, trace_id=trace_id)
    raise
finally:
    csv_manager.cleanup(request_id)
```

注意：request_id、trace_id 在 try 块开头已定义，except 中可访问。

**Step 2: 验证**

编写或运行会抛异常的查询测试，确认控制台和日志文件中有 QueryException 行。

---

## Task 6: Object.query 异常时调用 log_exception_stack

**Files:**
- Modify: `datacloud-data/src/datacloud_data/object.py`

**Step 1: 与 View.query 相同方式增加 except**

在 try/finally 之间增加：

```python
except Exception as exc:
    from datacloud_data_sdk.events.trace_logger import log_exception_stack
    log_exception_stack(exc, request_id=request_id, trace_id=trace_id)
    raise
```

**Step 2: 验证**

同 Task 5。

---

## Task 7: UnifiedQuery.execute 异常时调用 log_exception_stack

**Files:**
- Modify: `datacloud-data/src/datacloud_data_service/tools/unified_query.py`

**Step 1: 在 except 块中增加调用**

```python
except Exception as e:
    from datacloud_data_sdk.events.trace_logger import log_exception_stack
    log_exception_stack(e)  # 无 request_id/trace_id
    return {
        "content": [{"type": "text", "text": str(e)}],
        "isError": True,
    }
```

**Step 2: 验证**

触发 UnifiedQuery 捕获的异常（如 get_view 失败），确认栈信息输出。

---

## Task 8: EventTraceLogger 内部异常时调用 log_exception_stack

**Files:**
- Modify: `datacloud-data/src/datacloud_data/events/trace_logger.py`

**Step 1: 在 EventTraceLogger 的事件处理回调中**

序列化或写入失败时，除记录 logging 外，调用 `log_exception_stack(exc)`。

**Step 2: 验证**

可构造不可序列化的事件或只读文件路径，确认异常栈被输出。

---

## 验收检查清单

1. 查询请求触发时，控制台和 `logs/query_trace.log` 输出完整事件流（JSON 行）
2. 每行 JSON 包含 event_type、request_id、trace_id、timestamp、payload
3. DC_TRACE_LOG_PATH 未设置时使用 `logs/query_trace.log`
4. 写入失败不影响查询主流程
5. 异常发生时，栈信息输出到控制台和同一日志文件，格式为 `event_type: "QueryException"`

---

**Plan complete and saved to `docs/plans/2026-03-09-query-trace-console-and-file-implementation.md`.**

执行方式建议：
1. **Subagent-Driven（本会话）**：按任务分派子 agent，逐任务实现并审查
2. **Parallel Session（新会话）**：在新会话中用 executing-plans 按检查点批量执行
