# Multi-task flow Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement DAG-based planning/execution/end flow so multi-task queries return per-task and aggregated results.

**Architecture:** Enhance existing nodes (`planning`, `execution`, `end`) to share `PlanTask`/`TaskResult` contracts, append results in state, and produce final summary including files. No new nodes added; reuse runner wiring.

**Tech Stack:** Python 3.12, LangGraph nodes in `packages/datacloud-analysis`, pytests under `packages/datacloud-analysis/tests`.

---

## Chunk 1: Data Contracts & State Extensions

### Task 1: Define shared dataclasses and context helpers

**Files:**
- Modify: `packages/datacloud-analysis/src/datacloud_analysis/orchestration/shared/__init__.py`
- Modify: `packages/datacloud-analysis/src/datacloud_analysis/orchestration/shared/contracts.py` (new)
- Modify: `packages/datacloud-analysis/src/datacloud_analysis/orchestration/state.py`
- Test: `packages/datacloud-analysis/tests/dca/unit/test_state_multitask.py` (new)

- [ ] **Step 1:** Create `contracts.py` defining `PlanTask (todo_id: str, goal: str, required_tools: list[str], depends_on: list[str], inputs_from: dict[str, str], required_inputs: dict[str, bool])`, `ArtifactRef (todo_id: str, path: str, name: str, mime: str | None = None, size: int | None = None)`, `TaskError (code: str, message: str, tool: str | None = None, trace_id: str | None = None, remediation: str | None = None)`, `TaskResult (todo_id: str, status: Literal['success','failed','blocked'], result_meta: dict[str, Any], artifact_refs: list[ArtifactRef] = field(default_factory=list), error_detail: TaskError | None = None, blocked_by: str | Literal['missing_dependency', None] = None)` dataclasses with to/from dict helpers enforcing these invariants and defaults (use `field(default_factory=...)`).
- [ ] **Step 2:** Export these in `shared/__init__.py` for other modules.
- [ ] **Step 3:** Extend `WorkerState` helpers to: ensure defaults for `planned_tasks`, `task_queue`, `results_list`, `results_map`; set/return `planned_tasks` and queue order using serialization (store dicts, hydrate dataclasses on read); append `TaskResult`s while keeping `results_list`/`results_map` in sync; and prefill blocked entries (status='blocked', blocked_by='missing_dependency') when provided.
- [ ] **Step 4:** Add unit tests covering queue persistence, blocked prefill (seed missing dependency metadata and verify both `results_list`/`results_map` store sentinel values), append/lookup sync, round-trip serialization for each dataclass via the helpers, and negative cases (invalid status, missing todo_id, malformed artifact refs) to ensure the helpers reject bad payloads.

## Chunk 2: Planning Node DAG logic

### Task 2: Implement DAG planner with validation

**Files:**
- Modify: `packages/datacloud-analysis/src/datacloud_analysis/orchestration/planning/node.py`
- Modify: `packages/datacloud-analysis/src/datacloud_analysis/orchestration/planning/__init__.py`
- Test: `packages/datacloud-analysis/tests/dca/unit/test_planning_node.py`

- [ ] **Step 1:** Parse LLM planning output into `PlanTask` list, enforce unique `todo_id`, and parse each `inputs_from` expression into structured tokens (support `.result_meta.*` and `.artifact_refs[idx].*`), logging warnings for unknown fields while returning `None`.
- [ ] **Step 2:** For each `inputs_from`, ensure dependency edges exist (auto-add missing ones) and track referenced artifacts/fields for later diagnostics; build adjacency list.
- [ ] **Step 3:** Run topo sort, detect cycles, mark unreachable tasks as blocked with `missing_dependency`.
- [ ] **Step 4:** Persist `planned_tasks`, `task_queue`, and preblocked `TaskResult` into state; log diagnostics.
- [ ] **Step 5:** Update tests covering success, cycle, missing dep, `inputs_from` edge auto-add.

## Chunk 3: Execution Node with dependency injection

### Task 3: Build DAG executor

**Files:**
- Modify: `packages/datacloud-analysis/src/datacloud_analysis/orchestration/execution/node.py`
- Modify: `packages/datacloud-analysis/src/datacloud_analysis/orchestration/execution/react_runtime.py` (for task metadata + logs)
- Modify: `packages/datacloud-analysis/src/datacloud_analysis/orchestration/execution/__init__.py`
- Test: `packages/datacloud-analysis/tests/dca/unit/test_execution_node.py`

- [ ] **Step 1:** Iterate `task_queue`, skip tasks already in `results_map`.
- [ ] **Step 2:** Resolve `inputs_from` values, enforce `required_inputs`; if upstream failed/blocked propagate `blocked_by`; when referencing upstream artifacts, verify file existence/readability during injection and raise `TaskError(code='artifact_not_found', ...)` (status=`failed`) when missing; pass optional `None` injections downstream when allowed and log warnings.
- [ ] **Step 3:** Select the tools listed in `PlanTask.required_tools`, construct payload (user query, goal, injected params, todo_id), invoke existing tooling path; capture tool errors into `TaskError`.
- [ ] **Step 4:** Write artifacts under `tasks/<todo_id>/`, build `ArtifactRef` list (after verifying writes succeed; on failure emit generic `TaskError` with `code='artifact_write_failed'`), and ensure any `artifact_not_found` injection errors mark the task `status='failed'` before appending `TaskResult` to state.
- [ ] **Step 5:** Unit tests for success, tool failure, blocked-by-upstream, missing required input, artifact write error, missing optional inputs, and unresolved `inputs_from` artifact references (expect `artifact_not_found`).
- [ ] **Step 6:** Enhance execution logs (task start/end, duration, dependency resolution output, artifact paths, status changes, error codes) and extend `react_runtime` logs with candidate tools & model info per requirements.

## Chunk 4: End node aggregation & insight handoff

### Task 4: Multi-task final summary

**Files:**
- Modify: `packages/datacloud-analysis/src/datacloud_analysis/orchestration/end/node.py`
- Modify: `packages/datacloud-analysis/src/datacloud_analysis/orchestration/end/__init__.py`
- Modify: `packages/datacloud-analysis/src/datacloud_analysis/orchestration/insight/node.py` (if needed to consume final summary)
- Test: `packages/datacloud-analysis/tests/dca/unit/test_end_node.py`

- [ ] **Step 1:** Traverse `results_list`, generate per-task entries containing `todo_id`, `status`, textual summary (with required phrasing), `depends_on`, `blocked_by`, `result_meta`, and `artifact_refs`, using `PlanTask` metadata; use mandated copy for blocked (“任务 {todo} 因 {blocked_by} 失败/被阻断…”) and failed tasks referencing `error_detail`.
- [ ] **Step 2:** Build combined narrative (explicitly enumerating dependency relationships) and artifact_index structure; persist to `state.context['final_summary']`.
- [ ] **Step 3:** Ensure existing insight node reads new summary when present, fallback to legacy behavior otherwise, and add End-node logging for `returned_tasks`, `artifact_count`, blocked/failed summary counts.
- [ ] **Step 4:** Tests verifying multi-task summaries, blocked/failed messaging, artifact list output.

---

## Chunk 5: Integration & Regression

### Task 5: Wiring + tests

**Files:**
- Modify: `packages/datacloud-analysis/src/datacloud_analysis/orchestration/runner.py`
- Modify: `packages/datacloud-analysis/src/datacloud_analysis/orchestration/graph_builder.py`
- Test: `packages/datacloud-analysis/tests/dca/integration/test_multitask_flow.py`

- [ ] **Step 1:** Ensure runner/graph inject new context defaults and diagnostic logs before any node executes, including hydrating `planned_tasks`, `results_list`, `results_map` when resuming older checkpoints.
- [ ] **Step 2:** Add integration test simulating grid+enterprise tasks, assert two artifacts + final summary; add regression test covering single-task flow to ensure legacy path still works.
- [ ] **Step 3:** Run targeted `pytest` suites for planning/execution/end/integration.
- [ ] **Step 4:** Run `uv run ruff format .` followed by `uv run ruff check . --fix`.
- [ ] **Step 5:** Commit with message `feat(core): multi-task DAG flow`.
