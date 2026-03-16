# M4 知识库 + M5 Skills API 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现 M4 知识库（RAG HTTP 调用 + 标签检索）和 M5 Skills API（GET /api/v1/skills/package 返回 JSON）。

**Architecture:** M4：PlanStep type=KB → KbExecTask → KbExecutor HTTP 调用 RAG；M5：SkillPackageGenerator 复用 ToolRegistry + 生成 examples，REST 返回 JSON。

**Tech Stack:** httpx、dataclasses、FastAPI

---

## 执行顺序建议

**Phase A：M5 Skills API**（无依赖，可先交付）  
**Phase B：M4 知识库**（依赖 PlanGenerator、Executor 扩展）

---

# Phase A：M5 Skills API

## Task A1: SkillPackageGenerator 核心逻辑

**Files:**
- Create: `src/datacloud_data_service/tools/skill_package_generator.py`

**Step 1:** 创建 `SkillPackageGenerator`，复用 `ToolRegistry.list_tools(view_id, object_ids)`。若传 view_id，通过 `loader.get_view(view_id)` 取 objects，得到 object_ids 再调用 list_tools。

**Step 2:** 为每个 tool 增加 `examples` 字段（1–3 个占位示例，如 unified_data_query 用 `[{"question":"查询xxx"}]`）。

**Step 3:** 方法 `generate(view_id=None, object_ids=None) -> dict`，返回 `{version, view_id, view_name, tools}`。

**Step 4:** 运行 `pytest tests/ -v --tb=short` 确认无回归

**Step 5:** `git add` + `git commit -m "feat(skills): add SkillPackageGenerator"`

---

## Task A2: GET /api/v1/skills/package 路由

**Files:**
- Create: `src/datacloud_data_service/api/skills.py`
- Modify: `src/datacloud_data_service/api/routes.py`（include router）

**Step 1:** 创建 `skills.py`，`GET /package`，查询参数 `view_id`、`object_ids`，校验 X-Tenant-Id，至少传其一。

**Step 2:** 调用 `SkillPackageGenerator(loader).generate(...)`，返回 JSON。

**Step 3:** 在 `routes.py` 中 `app.include_router(skills_router, prefix="/api/v1")`

**Step 4:** 运行 `pytest tests/ -v --tb=short` 确认通过

**Step 5:** `git add` + `git commit -m "feat(api): add GET /api/v1/skills/package"`

---

## Task A3: Skills API 单元测试

**Files:**
- Create: `tests/datacloud_data_service/test_skills_api.py`

**Step 1:** 测试 `GET /api/v1/skills/package?view_id=xxx` 返回 200 且含 `tools`、`examples`。

**Step 2:** 测试缺少 X-Tenant-Id 返回 400。

**Step 3:** 测试未传 view_id 且未传 object_ids 返回 400。

**Step 4:** `git add` + `git commit -m "test(api): add skills package API tests"`

---

# Phase B：M4 知识库

## Task B1: KbExecTask + PlanStep type=KB

**Files:**
- Modify: `src/datacloud_data_sdk/executor/models.py`（新增 KbExecTask）
- Modify: `src/datacloud_data_sdk/plan/models.py`（PlanStep 新增 query、tags 字段）

**Step 1:** 在 `executor/models.py` 新增 `KbExecTask(datasource_alias, query, tags, output_ref)`。

**Step 2:** 在 `plan/models.py` 的 `PlanStep` 中新增 `query: str = ""`、`tags: dict = field(default_factory=dict)`。

**Step 3:** 运行 `pytest tests/ -v --tb=short` 确认通过

**Step 4:** `git add` + `git commit -m "feat(plan): add KbExecTask and PlanStep KB fields"`

---

## Task B2: ExecutionObjectConverter 支持 KB

**Files:**
- Modify: `src/datacloud_data_sdk/plan/execution_object_converter.py`

**Step 1:** 在 `_convert_step` 中新增 `elif step.type == "KB"`，返回 `KbExecTask(...)`。

**Step 2:** 修改 `convert` 返回类型包含 `KbExecTask`。

**Step 3:** 运行 `pytest tests/ -v --tb=short` 确认通过

**Step 4:** `git add` + `git commit -m "feat(plan): ExecutionObjectConverter support KB step"`

---

## Task B3: KbExecutor（KnowledgeBaseConnector）

**Files:**
- Create: `src/datacloud_data_sdk/executor/kb_executor.py`

**Step 1:** 创建 `KbExecutor`，接收 `kb_configs: dict[alias, {endpoint}]`，`execute(task: KbExecTask) -> list[dict]`。

**Step 2:** HTTP `POST {endpoint}/retrieve`，Body `{query, tags, top_k}`，解析 `{results: [...]}` 为 records。

**Step 3:** 配置来源：DataSourceConfig 扩展 `kb_endpoint`，或 LoaderConfig 新增 `kb_source_configs: dict`。

**Step 4:** 运行 `pytest tests/ -v --tb=short` 确认通过

**Step 5:** `git add` + `git commit -m "feat(executor): add KbExecutor for RAG HTTP"`

---

## Task B4: Executor 集成 KbExecutor

**Files:**
- Modify: `src/datacloud_data_sdk/executor/executor.py`
- Modify: `src/datacloud_data_sdk/view.py`、`src/datacloud_data_sdk/object.py`（创建 KbExecutor 并传入）

**Step 1:** Executor 新增 `kb_executor` 参数，在 `run` 中处理 `KbExecTask`。

**Step 2:** KB 结果写入 CSV 或直接返回 records；若聚合层期望 CSV，需 `ResultConverter` 或临时 CSV 写入。

**Step 3:** View.query / Object.query 在创建 Executor 时构造 KbExecutor（若 config 含 kb 配置）。

**Step 4:** 运行 `pytest tests/ -v --tb=short` 确认通过

**Step 5:** `git add` + `git commit -m "feat(executor): wire KbExecutor into Executor"`

---

## Task B5: PlanGenerator 支持 KB 步骤

**Files:**
- Modify: `src/datacloud_data_sdk/plan/query_plan_generator.py`（LangGraphPlanGenerator 的 prompt）
- Modify: `src/datacloud_data_sdk/plan/query_plan_generator.py`（MockPlanGenerator 支持 KB）

**Step 1:** 在 LLM prompt 中说明：当 ObjectView 含 source_type=KNOWLEDGE_BASE 时，可生成 type=KB 的 step，含 query、tags。

**Step 2:** MockPlanGenerator 可接受 `validation_errors` 和 `kb_steps` 参数，便于测试。

**Step 3:** 运行 `pytest tests/ -v --tb=short` 确认通过

**Step 4:** `git add` + `git commit -m "feat(plan): PlanGenerator support KB step"`

---

## Task B6: M4 单元测试

**Files:**
- Create: `tests/datacloud_data_sdk/test_kb_executor.py`
- Modify: `tests/datacloud_data_sdk/test_execution_object_converter.py`（KB 步骤转换）

**Step 1:** 测试 ExecutionObjectConverter 将 type=KB 的 PlanStep 转为 KbExecTask。

**Step 2:** 测试 KbExecutor：mock httpx，验证请求体含 query、tags，响应解析为 records。

**Step 3:** `git add` + `git commit -m "test(executor): add KB executor tests"`

---

## 执行选项

计划已保存至 `docs/plans/2026-03-08-m4-m5-implementation.md`。

**建议**：先执行 Phase A（M5），再执行 Phase B（M4）。

**执行方式**：
1. Subagent-Driven（本会话）
2. Parallel Session（新会话）
