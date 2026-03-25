# M3: 可观测性 v1 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现事件驱动可观测（QueryObserver 接入管线）、计划校验失败自动重试、请求级性能日志（含模块输入输出摘要）。

**Architecture:** LoaderConfig 新增 event_bus；lifespan 创建 EventBus + TracingMiddleware，注册 handlers 与性能日志回调；View/Object.query() 在 event_bus 存在时创建 QueryObserver 发布事件；计划重试在管线内用 for 循环包裹 generate→validate；性能日志由 on_span_complete 聚合并输出 JSON。

**Tech Stack:** 现有 EventBus、TracingMiddleware、EventSpan、QueryObserver；Python logging、json

---

## Task 1: LoaderConfig 新增 event_bus

**Files:**
- Modify: `src/datacloud_data/ontology/loader.py`

**Step 1:** 在 `LoaderConfig` 中新增 `event_bus: EventBus | None = None`（需 `from typing import TYPE_CHECKING` 和 `if TYPE_CHECKING: from datacloud_data_sdk.events.bus import EventBus` 避免循环导入，或直接 `Any`）

**Step 2:** 运行 `pytest tests/datacloud_data/test_ontology_loader.py -v`，确认通过

**Step 3:** `git add` + `git commit -m "feat(loader): add event_bus to LoaderConfig"`

---

## Task 2: register_query_handlers 支持 TracingMiddleware

**Files:**
- Modify: `src/datacloud_data/events/handlers.py`
- Test: `tests/datacloud_data/test_event_handlers.py`

**Step 1:** 扩展 `register_query_handlers(bus, on_event=None, tracing=None)`。若 `tracing` 非空，对每个事件类型调用 `tracing.subscribe(event_cls, async_noop, "query")`；否则保持原逻辑 `bus.subscribe(event_cls, _async_on_event)`。

**Step 2:** 添加测试 `test_register_handlers_with_tracing_subscribes_via_tracing`，验证 tracing 传入时使用 tracing.subscribe。

**Step 3:** `git add` + `git commit -m "feat(events): register_query_handlers support TracingMiddleware"`

---

## Task 3: TracingMiddleware 填充 EventSpan input_summary

**Files:**
- Modify: `src/datacloud_data/events/tracing.py`
- Test: `tests/datacloud_data/test_tracing.py`

**Step 1:** 新增 `_event_to_input_summary(event: BaseEvent) -> dict`，按事件类型返回摘要（如 QueryRequestReceived → `{"question_len": len(question), "object_ids": object_ids}`）。

**Step 2:** 在 `traced_handler` 的 `finally` 中，创建 EventSpan 时设置 `input_summary=_event_to_input_summary(event)`。

**Step 3:** 扩展测试验证 span 含 input_summary。

**Step 4:** `git add` + `git commit -m "feat(events): TracingMiddleware populates EventSpan input_summary"`

---

## Task 4: QueryObserver 补齐事件 + View.query 接入

**Files:**
- Modify: `src/datacloud_data/events/query_observer.py`
- Modify: `src/datacloud_data/view.py`
- Test: `tests/datacloud_data/test_view.py` 或新增集成测试

**Step 1:** QueryObserver 新增 `on_plan_validated(request_id, valid, plan, errors, retry_count)`、`on_plan_rewritten`、`on_execution_tasks_ready`（若 events 中有对应类型）。

**Step 2:** View.query() 开头：若 `config.event_bus` 非空，创建 `QueryObserver(config.event_bus, trace_id)`；在 builder.build 后调用 `observer.on_view_built`；在 plan 生成后调用 `observer.on_plan_generated`；在 validate 后调用 `observer.on_plan_validated`；在 DPR 后调用 `observer.on_plan_rewritten`；在 convert 后调用 `observer.on_execution_tasks_ready`；在 executor.run 后调用 `observer.on_steps_executed`；在 aggregate 后调用 `observer.on_aggregation_completed`。所有 observer 调用包在 try/except 中吞异常。

**Step 3:** 添加测试：View.query 在 event_bus 注入时，EventBus 能收到事件（mock bus.publish 或收集事件）。

**Step 4:** `git add` + `git commit -m "feat(events): wire QueryObserver into View.query"`

---

## Task 5: Object.query 接入 QueryObserver

**Files:**
- Modify: `src/datacloud_data/object.py`

**Step 1:** 与 View.query 类似，在 Object.query 各阶段调用 observer.on_*（Object 为单对象，部分事件可能简化）。

**Step 2:** 运行 `pytest tests/ -v` 确认通过。

**Step 3:** `git add` + `git commit -m "feat(events): wire QueryObserver into Object.query"`

---

## Task 6: lifespan 创建 EventBus 并注册

**Files:**
- Modify: `src/datacloud_data_service/api/routes.py`

**Step 1:** 在 lifespan 中：`bus = EventBus()`，`tracing = TracingMiddleware(bus)`，`register_query_handlers(bus, tracing=tracing)`，`loader.configure(event_bus=bus)`。

**Step 2:** 运行 `pytest tests/datacloud_data_service/ -v` 确认通过。

**Step 3:** `git add` + `git commit -m "feat(service): lifespan creates EventBus and registers handlers"`

---

## Task 7: 计划重试循环

**Files:**
- Modify: `src/datacloud_data/view.py`
- Modify: `src/datacloud_data/object.py`
- Test: 新增 `tests/datacloud_data/test_plan_retry.py`

**Step 1:** 在 View.query 中，用 `max_retries = getattr(config.plan_generator, '_max_retries', 2)` 或从 Settings 读取。将「generate → validate」放入 `for retry in range(max_retries + 1)`。校验失败时，`plan = await config.plan_generator.generate(payload, question, validation_errors=result.errors)` 并继续循环；成功则 break。超次数则 `raise PlanValidationError(result.errors)`。

**Step 2:** Object.query 同样逻辑。

**Step 3:** 添加测试：MockPlanGenerator 返回无效计划，验证重试次数与最终抛出。

**Step 4:** `git add` + `git commit -m "feat(plan): add plan validation retry loop"`

---

## Task 8: 性能日志 on_span_complete 聚合与输出

**Files:**
- Modify: `src/datacloud_data_service/api/routes.py`
- Create: `src/datacloud_data_service/events/performance_logger.py`（可选，或内联在 routes）

**Step 1:** 创建 `PerformanceLogHandler`：维护 `spans_by_request: dict[str, list[EventSpan]]`。`on_span(span)` 将 span 加入 `spans_by_request[span.request_id]`。需在收到 `AggregationCompleted` 或 `PlanValidationFailed` 时触发汇总——可通过 register_query_handlers 的 on_event 回调，当事件为结束类型时，从 event.request_id 取 spans，计算 total_ms，输出 JSON 到 stdout（`print(json.dumps({...}), flush=True)` 或 `logging.info`），并清理 `spans_by_request[request_id]`。

**Step 2:** 在 lifespan 中：创建 handler，`tracing.on_span_complete(handler.on_span)`；在 `register_query_handlers` 的 on_event 中，若事件为 AggregationCompleted/PlanValidationFailed，调用 handler.flush(request_id)。

**Step 3:** 输出格式：`{"event":"query_performance","request_id":...,"trace_id":...,"stages":[...],"total_ms":...}`，每个 stage 含 `module`、`event_in`、`duration_ms`、`input`（来自 input_summary）、`output`（若有）。

**Step 4:** 添加测试：mock 事件流，验证输出 JSON 结构。

**Step 5:** `git add` + `git commit -m "feat(service): request-level performance log with input/output summary"`

---

## Task 9: 端到端验证

**Step 1:** 运行 `pytest tests/ -v`，全部通过。

**Step 2:** 启动服务，调用 `/api/v1/query`，检查 stdout 是否有 `query_performance` JSON 日志。

**Step 3:** `git add` + `git commit -m "chore(m3): e2e verification"`

---

## 执行顺序

| 顺序 | Task | 预计时间 |
|------|------|---------|
| 1 | Task 1: LoaderConfig event_bus | 5 min |
| 2 | Task 2: handlers 支持 tracing | 10 min |
| 3 | Task 3: TracingMiddleware input_summary | 15 min |
| 4 | Task 4: QueryObserver + View.query | 20 min |
| 5 | Task 5: Object.query 接入 | 10 min |
| 6 | Task 6: lifespan EventBus | 10 min |
| 7 | Task 7: 计划重试 | 15 min |
| 8 | Task 8: 性能日志 | 20 min |
| 9 | Task 9: 端到端验证 | 10 min |
