# 查询跟踪信息输出（控制台 + 日志文件）设计

**日期**: 2026-03-09  
**目标**: 将查询管线的完整事件流输出到控制台和日志文件，便于调试与可观测性。

---

## 1. 需求摘要

| 项目 | 说明 |
|------|------|
| 跟踪信息 | 完整事件流，每个事件都输出 |
| 输出目标 | 控制台 + 日志文件 |
| 日志路径 | 环境变量 `DC_TRACE_LOG_PATH`，默认 `logs/query_trace.log` |
| 输出格式 | JSON 行（每行一个 JSON 对象） |
| 异常栈 | 异常发生时，栈信息输出到控制台和同一日志文件 |

---

## 2. 架构

采用 **方案 B：EventBus 直接订阅 + 事件序列化**。

- 新增 `EventTraceLogger`，直接订阅 EventBus 的查询相关事件
- 每个事件序列化为 JSON 行，同时写入控制台和文件
- 与现有 TracingMiddleware 并行，不修改 TracingMiddleware

**数据流**：

```
QueryObserver 发布事件 → EventBus
    → TracingMiddleware（现有，记录 span）
    → EventTraceLogger（新增，输出到控制台 + 文件）
```

---

## 3. 组件设计

### 3.1 EventTraceLogger

- **职责**：订阅事件，序列化后输出到控制台和文件
- **位置**：`datacloud_data_sdk/events/trace_logger.py`
- **接口**：
  - `__init__(trace_log_path: str, enabled: bool = True)`
  - `register(bus: EventBus)`：订阅所有查询事件类型

### 3.2 事件序列化

- 将 `BaseEvent` 子类转为可 JSON 序列化的 dict
- 使用 `dataclasses.asdict` 或手动提取字段
- 输出结构：`{"event_type": "QueryRequestReceived", "request_id": "...", "trace_id": "...", "timestamp": "...", "payload": {...}}`
- `timestamp`：ISO 8601 格式
- `payload`：事件特有字段（question、plan、object_view 等）

### 3.3 输出目标

- **控制台**：`sys.stderr` 或 `print(..., file=sys.stderr)`
- **文件**：按路径追加写入，每次写入一行 JSON + 换行
- 文件不存在时自动创建目录（`Path(path).parent.mkdir(parents=True, exist_ok=True)`）

---

## 4. 配置

在 `datacloud_data_service/config.py` 的 `Settings` 中增加：

```python
trace_log_path: str = "logs/query_trace.log"  # 环境变量 DC_TRACE_LOG_PATH
trace_enabled: bool = True                     # 可选，环境变量 DC_TRACE_ENABLED
```

---

## 5. 集成点

在 `datacloud_data_service/api/routes.py` 的 `create_app` 中，`register_query_handlers` 之后：

- 若 `trace_enabled` 为 True，创建 `EventTraceLogger(settings.trace_log_path)` 并调用 `register(bus)`
- EventBus 支持多订阅者，TraceLogger 与 TracingMiddleware 并行接收同一事件，互不影响

---

## 6. 错误处理

- 写入文件失败（磁盘满、权限不足）：捕获异常，记录到 `logging`，不中断主流程
- 序列化失败（如不可 JSON 序列化的对象）：捕获，输出 `{"event_type": "X", "error": "serialization failed"}`

---

## 7. 异常栈信息输出

当查询管线或 TraceLogger 自身发生异常时，将完整栈信息输出到控制台和日志文件。

### 7.1 范围

| 场景 | 说明 |
|------|------|
| 查询管线异常 | View.query / Object.query 执行过程中抛出的异常 |
| UnifiedQuery 异常 | execute() 捕获的异常（含 view/object 未捕获的） |
| TraceLogger 自身异常 | 事件序列化、写入失败等，在记录到 logging 的同时输出栈到控制台和文件 |

### 7.2 实现方式

- 新增工具函数 `log_exception_stack(exc, request_id=None, trace_id=None, path=None)`
- 使用 `traceback.format_exc()` 获取完整栈
- 输出目标：`sys.stderr`（控制台）+ 追加到 trace 日志文件（与事件共用 `DC_TRACE_LOG_PATH`）
- 文件格式：JSON 行，与事件一致，便于统一解析

### 7.3 输出格式

```json
{
  "event_type": "QueryException",
  "request_id": "uuid 或空",
  "trace_id": "trace_id 或空",
  "timestamp": "ISO 8601",
  "exception": "ExceptionType: message",
  "traceback": "完整 traceback 文本"
}
```

### 7.4 集成点

| 位置 | 行为 |
|------|------|
| View.query | 在 `try` 外增加 `except`，捕获后调用 `log_exception_stack(exc, request_id, trace_id)`，再 `raise` |
| Object.query | 同上 |
| UnifiedQuery.execute | 在 `except` 中调用 `log_exception_stack(e)`（无 request_id 时传 None） |
| EventTraceLogger | 在内部 `except` 中，除 logging 外再调用 `log_exception_stack(exc)` |

### 7.5 工具函数位置与路径

- 放在 `datacloud_data_sdk/events/trace_logger.py` 中，与 EventTraceLogger 同模块
- `path=None` 时，从环境变量 `DC_TRACE_LOG_PATH` 读取，默认 `logs/query_trace.log`，与事件日志共用

---

## 8. 事件类型列表

与 `register_query_handlers` 中的 `all_event_types` 一致：

- QueryRequestReceived
- ObjectViewBuilt
- QueryPlanGenerated
- PlanValidated
- PlanRewritten
- ExecutionTasksReady
- StepsExecuted
- AggregationCompleted
- PlanValidationFailed

---

## 9. 验收标准

1. 查询请求触发时，控制台和 `logs/query_trace.log`（或 DC_TRACE_LOG_PATH 指定路径）均输出完整事件流
2. 每行一个 JSON 对象，包含 event_type、request_id、trace_id、timestamp、payload
3. DC_TRACE_LOG_PATH 未设置时使用默认值 `logs/query_trace.log`
4. 写入失败不影响查询主流程
5. 异常发生时，栈信息输出到控制台和同一日志文件，格式为 `event_type: "QueryException"` 的 JSON 行
