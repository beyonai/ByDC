# M3: 可观测性 v1 设计

> **日期**：2026-03-08
> **状态**：已确认
> **范围**：#75 handlers 事件链、#76 计划重试、#79 性能日志

---

## 1 目标

实现 M3 可观测性 v1：事件驱动可观测、计划校验失败自动重试、请求级性能日志（含模块输入输出摘要）。

---

## 2 架构总览

- **LoaderConfig** 新增 `event_bus`，由 lifespan 创建 EventBus、注册 TracingMiddleware 与 handlers
- **View.query() / Object.query()** 接入 QueryObserver 发布事件
- **计划重试**：校验失败时在管线内重试（最多 `max_retries` 次）
- **性能日志**：通过 TracingMiddleware 的 `on_span_complete` 收集，由 lifespan 注册的 handler 输出

**数据流**：`View.query() → QueryObserver.on_*() → EventBus.publish() → TracingMiddleware 包装的 handlers → on_span_complete → 性能日志`

**不改动**：主执行路径仍为直接调用，事件仅用于可观测性。

---

## 3 handlers.py + EventBus 接入

### 3.1 LoaderConfig 扩展

- `LoaderConfig` 新增 `event_bus: EventBus | None = None`
- 通过 `loader.configure(event_bus=bus)` 注入

### 3.2 服务层 lifespan

- 创建 `EventBus()` 实例
- 创建 `TracingMiddleware(bus)`，用 `tracing.subscribe()` 包装各事件类型的 handler
- 调用 `register_query_handlers`，改为接收 `TracingMiddleware` 或通过 tracing 注册
- 在 `tracing.on_span_complete()` 注册性能日志回调
- 执行 `loader.configure(event_bus=bus)`

### 3.3 View.query() / Object.query() 接入 QueryObserver

- 从 `config` 读取 `event_bus`
- 若 `event_bus` 非空：创建 `QueryObserver(bus, trace_id)`，在各阶段调用 `observer.on_*()`
- 若为空：不创建 observer，保持原行为
- 补齐 QueryObserver 缺失事件：`PlanValidated`、`PlanRewritten`、`ExecutionTasksReady`（若当前未覆盖）

### 3.4 handlers 与 TracingMiddleware

- lifespan 中使用 TracingMiddleware 的 `subscribe`，而非直接 `bus.subscribe`
- `register_query_handlers` 改为接收 `TracingMiddleware`，内部对每个事件调用 `tracing.subscribe(event_cls, noop_handler, "query")`

---

## 4 计划校验失败自动重试（#76）

**触发条件**：`PlanValidator.validate()` 返回 `valid=False` 且 `plan.can_answer=True`。

**重试逻辑**：
- 用 `for retry in range(max_retries + 1)` 包裹「生成计划 → 校验」
- 校验失败时：`plan_generator.generate(payload, question, validation_errors=result.errors)` 重新生成
- 超过 `max_retries` 仍失败：抛出 `PlanValidationError(result.errors)`
- `max_retries` 从 config/Settings 读取，默认 2

**不重试**：`CannotAnswerError`（`can_answer=False`）直接抛出。

---

## 5 请求级性能日志（#79）

### 5.1 收集方式

TracingMiddleware 的 `on_span_complete` 回调。

### 5.2 实现

- 用 `request_id` 聚合同一请求的 spans：`dict[request_id, list[EventSpan]]`
- `on_span_complete`：将 span 加入对应 `request_id` 的列表
- 收到 `AggregationCompleted` 或 `PlanValidationFailed` 等结束事件时：汇总该 `request_id` 的 spans，输出一条 JSON 日志，清理缓存

### 5.3 TracingMiddleware 填充 input_summary

从事件 payload 生成摘要：
- `QueryRequestReceived` → `{"question_len": N, "object_ids": [...]}`
- `ObjectViewBuilt` → `{"object_count": N}`
- `QueryPlanGenerated` → `{"step_count": N, "can_answer": bool}`
- `PlanValidated` → `{"valid": bool, "error_count": N}`
- `StepsExecuted` → `{"step_count": N}`
- `AggregationCompleted` → `{"record_count": N, "column_count": N}`

### 5.4 输出格式（stdout）

```json
{
  "event": "query_performance",
  "request_id": "x",
  "trace_id": "y",
  "stages": [
    {"module": "query", "event_in": "ObjectViewBuilt", "duration_ms": 5, "input": {"object_count": 2}},
    {"module": "query", "event_in": "QueryPlanGenerated", "duration_ms": 1200, "input": {"step_count": 1, "can_answer": true}},
    {"module": "query", "event_in": "AggregationCompleted", "duration_ms": 10, "input": {}, "output": {"record_count": 5, "column_count": 3}}
  ],
  "total_ms": 1250
}
```

**隐私**：input/output 仅记录统计摘要，不记录完整 question、plan、records。

---

## 6 测试与错误处理

**测试**：
- 单元：`register_query_handlers` + TracingMiddleware 时，发布事件能触发 span 回调
- 集成：`View.query()` 在 `event_bus` 注入时发布事件；无 bus 时行为不变
- 计划重试：校验失败后重试，超 `max_retries` 抛出
- 性能日志：`on_span_complete` 收到 spans，`input_summary` 正确

**错误处理**：
- QueryObserver 发布事件时 `try/except` 吞异常，不影响主流程
- TracingMiddleware handler 异常向上抛出，span 记录 `status="error"`
- 性能日志 handler 异常仅打 log，不中断请求
