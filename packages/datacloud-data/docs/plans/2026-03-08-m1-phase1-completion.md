# M1: Phase 1 收尾 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 补齐 Phase 1 剩余 10 项功能——PlanValidator 增强、事件处理链、MCP 专项测试、CRM 端到端测试、sql_execution_mode 切换。

**Architecture:** 所有改动在现有模块上增量添加，不引入新包。PlanValidator 新增两个校验方法；handlers.py 注册 EventBus 订阅者串联查询事件；测试用 MockPlanGenerator + SQLite + httpx mock 验证完整流水线。

**Tech Stack:** Python 3.12, pytest, pytest-asyncio, pytest-mock, httpx, FastAPI TestClient

---

## Task 1: PlanValidator SQL 字段引用校验（#20）

**Files:**
- Modify: `src/datacloud_data_sdk/plan/plan_validator.py`
- Test: `tests/datacloud_data_sdk/test_plan_validator.py`

**Step 1: Write the failing test**

```python
# 追加到 tests/datacloud_data_sdk/test_plan_validator.py

def test_sql_field_ref_not_in_object_view_fails():
    """SQL 中引用了 ObjectView 不存在的字段时校验失败。"""
    from datacloud_data_sdk.plan.plan_validator import PlanValidator, ValidationResult
    from datacloud_data_sdk.plan.models import (
        ObjectViewPayload, ObjectViewSource, ObjectViewObject, ObjectViewField,
        QueryExecutionPlan, PlanStep, PlanAggregation,
    )

    payload = ObjectViewPayload(
        view_id="v1",
        sources=[ObjectViewSource(source_id="SRC_DB", source_type="DB", datasource_alias="db1")],
        objects=[
            ObjectViewObject(
                object_id="obj1", object_name="测试对象", source_id="SRC_DB",
                table="t_test",
                fields=[
                    ObjectViewField(name="id", type="string"),
                    ObjectViewField(name="name", type="string"),
                ],
            )
        ],
    )
    plan = QueryExecutionPlan(
        question="test",
        can_answer=True,
        steps=[
            PlanStep(
                step_id="s1", type="SQL", source_id="SRC_DB",
                datasource_alias="db1",
                sql_template="SELECT id, name, nonexistent_field FROM t_test",
                output_ref="out",
            )
        ],
        aggregation=PlanAggregation(strategy="DIRECT", final_step_id="s1"),
    )
    result = PlanValidator().validate(plan, payload)
    assert not result.valid
    assert any("nonexistent_field" in e for e in result.errors)


def test_sql_field_ref_valid_passes():
    """SQL 中引用的字段全部存在于 ObjectView 时校验通过。"""
    from datacloud_data_sdk.plan.plan_validator import PlanValidator
    from datacloud_data_sdk.plan.models import (
        ObjectViewPayload, ObjectViewSource, ObjectViewObject, ObjectViewField,
        QueryExecutionPlan, PlanStep, PlanAggregation,
    )

    payload = ObjectViewPayload(
        view_id="v1",
        sources=[ObjectViewSource(source_id="SRC_DB", source_type="DB", datasource_alias="db1")],
        objects=[
            ObjectViewObject(
                object_id="obj1", object_name="测试对象", source_id="SRC_DB",
                table="t_test",
                fields=[
                    ObjectViewField(name="id", type="string"),
                    ObjectViewField(name="name", type="string"),
                ],
            )
        ],
    )
    plan = QueryExecutionPlan(
        question="test",
        can_answer=True,
        steps=[
            PlanStep(
                step_id="s1", type="SQL", source_id="SRC_DB",
                datasource_alias="db1",
                sql_template="SELECT id, name FROM t_test WHERE id = '1'",
                output_ref="out",
            )
        ],
        aggregation=PlanAggregation(strategy="DIRECT", final_step_id="s1"),
    )
    result = PlanValidator().validate(plan, payload)
    assert result.valid
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/datacloud_data_sdk/test_plan_validator.py::test_sql_field_ref_not_in_object_view_fails -v
```
Expected: FAIL

**Step 3: Implement — 在 PlanValidator 中添加 SQL 字段引用提取与校验**

在 `plan_validator.py` 中添加方法 `_validate_sql_field_refs`：
- 用正则从 `SELECT ... FROM`、`WHERE`、`JOIN ON` 中提取列名（排除 SQL 函数、字符串常量、`*`、别名）
- 收集 ObjectViewPayload 中所有 objects 的 field.name + table 名到一个 `known_names` 集合
- 将 SQL 提取的列名与 known_names 取差集，未知列名加入 errors

在 `validate()` 方法中调用此新方法。

**Step 4: Run tests to verify they pass**

```bash
pytest tests/datacloud_data_sdk/test_plan_validator.py -v
```
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/datacloud_data_sdk/plan/plan_validator.py tests/datacloud_data_sdk/test_plan_validator.py
git commit -m "feat(plan): add SQL field reference validation to PlanValidator"
```

---

## Task 2: PlanValidator function_id 校验（#21）

**Files:**
- Modify: `src/datacloud_data_sdk/plan/plan_validator.py`
- Test: `tests/datacloud_data_sdk/test_plan_validator.py`

**Step 1: Write the failing test**

```python
def test_api_step_unknown_function_id_fails():
    """API 步骤的 function_id 不在 ObjectView 中时校验失败。"""
    from datacloud_data_sdk.plan.plan_validator import PlanValidator
    from datacloud_data_sdk.plan.models import (
        ObjectViewPayload, ObjectViewSource, ObjectViewObject, ObjectViewField,
        ObjectViewFunction, QueryExecutionPlan, PlanStep, PlanAggregation,
    )

    payload = ObjectViewPayload(
        view_id="v1",
        sources=[ObjectViewSource(source_id="SRC_API", source_type="API")],
        objects=[
            ObjectViewObject(
                object_id="obj1", object_name="测试对象", source_id="SRC_API",
                fields=[ObjectViewField(name="id", type="string")],
                functions=[ObjectViewFunction(function_code="fn_real")],
            )
        ],
    )
    plan = QueryExecutionPlan(
        question="test",
        can_answer=True,
        steps=[
            PlanStep(step_id="s1", type="API", source_id="SRC_API",
                     function_id="fn_nonexistent", output_ref="out")
        ],
        aggregation=PlanAggregation(strategy="DIRECT", final_step_id="s1"),
    )
    result = PlanValidator().validate(plan, payload)
    assert not result.valid
    assert any("fn_nonexistent" in e for e in result.errors)
```

**Step 2: Run test — expected FAIL**

**Step 3: Implement — 在 validate() 中收集 payload 的 function_codes，校验 API 步骤 function_id**

**Step 4: Run tests — expected ALL PASS**

**Step 5: Commit**

```bash
git commit -m "feat(plan): add function_id existence validation"
```

---

## Task 3: handlers.py 事件处理链注册（#43）

**Files:**
- Create: `src/datacloud_data_sdk/events/handlers.py`
- Test: `tests/datacloud_data_sdk/test_event_handlers.py`

**Step 1: Write the failing test**

```python
import pytest
from datacloud_data_sdk.events.bus import EventBus
from datacloud_data_sdk.events.events import QueryRequestReceived, ObjectViewBuilt
from datacloud_data_sdk.events.handlers import register_query_handlers


@pytest.mark.asyncio
async def test_register_handlers_subscribes_to_events():
    """register_query_handlers 注册后，发布事件能被处理。"""
    bus = EventBus()
    received = []
    register_query_handlers(bus, on_event=lambda e: received.append(e))
    bus.publish(QueryRequestReceived(request_id="r1", trace_id="t1"))
    assert len(received) == 1
    assert received[0].request_id == "r1"
```

**Step 2: Run test — expected FAIL**

**Step 3: Implement handlers.py**

```python
"""事件处理链注册：将查询管线各阶段事件串联到 EventBus。"""
from __future__ import annotations
from typing import Any, Callable
from datacloud_data_sdk.events.bus import EventBus
from datacloud_data_sdk.events.events import (
    QueryRequestReceived, ObjectViewBuilt, QueryPlanGenerated,
    PlanValidated, PlanRewritten, ExecutionTasksReady,
    StepExecuted, AggregationCompleted,
)

ALL_QUERY_EVENTS = [
    QueryRequestReceived, ObjectViewBuilt, QueryPlanGenerated,
    PlanValidated, PlanRewritten, ExecutionTasksReady,
    StepExecuted, AggregationCompleted,
]


def register_query_handlers(
    bus: EventBus,
    on_event: Callable[[Any], None] | None = None,
) -> None:
    """注册查询管线所有事件类型的处理器。

    on_event 回调在每个事件被发布时触发，用于日志、追踪等。
    """
    for event_cls in ALL_QUERY_EVENTS:
        if on_event:
            bus.subscribe(event_cls.__name__, on_event)
```

**Step 4: Run tests — expected ALL PASS**

**Step 5: Commit**

```bash
git commit -m "feat(events): add handlers.py with register_query_handlers"
```

---

## Task 4: MCP tools/call 操作类工具专项测试（#58）

**Files:**
- Create: `tests/datacloud_data_service/test_mcp_tools_call_action.py`

**Step 1: Write the test**

```python
"""MCP tools/call 操作类工具测试：ParamMapper → TermResolver → invoke_action 完整流水线。"""
import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from datacloud_data_sdk.ontology.loader import OntologyLoader

HEADERS = {
    "X-Tenant-Id": "t1",
    "X-User-Id": "u1",
    "Authorization": "Bearer tok",
}

REGISTRY = {
    "functions": [
        {
            "function_code": "fn_query_bo",
            "api_schema": {
                "servers": [{"url": "http://mock-api:8080"}],
                "paths": {"/api/bo/query": {}},
            },
        }
    ],
    "objects": [
        {
            "object_code": "sales_bo",
            "object_name": "商机",
            "source_type": "API",
            "fields": [],
            "actions": [
                {
                    "action_code": "query_bo_by_owner",
                    "action_name": "按负责人查商机",
                    "description": "通过负责人ID查询商机列表",
                    "function_refs": ["fn_query_bo"],
                    "params": [
                        {"param_code": "owner_id", "param_name": "负责人ID",
                         "param_type": "STRING", "direction": "IN", "required": True},
                    ],
                },
                {
                    "action_code": "calc_score",
                    "action_name": "计算评分",
                    "script": "def execute(params):\n    return {'score': 100}",
                    "function_refs": [],
                    "params": [
                        {"param_code": "bo_id", "param_type": "STRING", "direction": "IN"},
                        {"param_code": "score", "param_type": "NUMBER", "direction": "OUT"},
                    ],
                },
            ],
        }
    ],
    "relations": [],
}


def _create_app():
    from datacloud_data_service.api.routes import create_app
    app = create_app()
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    app.state.loader = loader
    return app


def test_tools_list_includes_action_tools():
    """tools/list 返回 unified_data_query + 操作类工具。"""
    client = TestClient(_create_app())
    resp = client.post("/api/v1/mcp", json={
        "jsonrpc": "2.0", "id": "1", "method": "tools/list", "params": {},
    }, headers=HEADERS)
    tools = resp.json()["result"]["tools"]
    names = [t["name"] for t in tools]
    assert "unified_data_query" in names
    assert "query_bo_by_owner" in names
    assert "calc_score" in names


def test_tools_call_script_action():
    """tools/call 脚本动作直接执行返回结果。"""
    client = TestClient(_create_app())
    resp = client.post("/api/v1/mcp", json={
        "jsonrpc": "2.0", "id": "2", "method": "tools/call",
        "params": {"name": "calc_score", "arguments": {"bo_id": "B001"}},
    }, headers=HEADERS)
    result = resp.json()["result"]
    assert result["isError"] is False
    assert "100" in result["content"][0]["text"]


def test_tools_call_unknown_action_returns_error():
    """tools/call 未知工具返回错误。"""
    client = TestClient(_create_app())
    resp = client.post("/api/v1/mcp", json={
        "jsonrpc": "2.0", "id": "3", "method": "tools/call",
        "params": {"name": "nonexistent_tool", "arguments": {}},
    }, headers=HEADERS)
    result = resp.json()["result"]
    assert result["isError"] is True
```

**Step 2: Run tests**

```bash
pytest tests/datacloud_data_service/test_mcp_tools_call_action.py -v
```
Expected: ALL PASS（这些测试验证已实现的功能）

**Step 3: Commit**

```bash
git commit -m "test(service): add MCP tools/call action tests"
```

---

## Task 5: CRM 端到端场景测试（#59）

**Files:**
- Create: `tests/e2e/test_crm_scenarios.py`

**Step 1: Write tests**

5 个核心场景，使用 MockPlanGenerator + SQLite 模拟：

1. 自然语言查询「查商机」→ 返回 records
2. 跨数据源 → SQLITE_MEM 聚合
3. 不可回答 → CannotAnswerError
4. MCP 操作类工具 → invoke_action
5. 脚本动作执行 → ScriptExecutor

每个场景约 20-30 行测试代码，使用 `resources/ontology/crm_demo/objects_registry.json` 做真实本体加载。

**Step 2: Run tests**

```bash
pytest tests/e2e/test_crm_scenarios.py -v
```

**Step 3: Commit**

```bash
git commit -m "test(e2e): add 5 CRM end-to-end scenario tests"
```

---

## Task 6: sql_execution_mode 切换（#60）

**Files:**
- Modify: `src/datacloud_data_service/config.py`
- Modify: `src/datacloud_data_sdk/ontology/loader.py`（LoaderConfig 新增字段）
- Test: `tests/datacloud_data_sdk/test_ontology_loader.py`

**Step 1: Write test**

```python
def test_configure_sql_execution_mode():
    loader = OntologyLoader()
    loader.configure(sql_execution_mode="external")
    assert loader._config.sql_execution_mode == "external"
```

**Step 2: Run test — expected FAIL**

**Step 3: Implement**

- `LoaderConfig` 新增 `sql_execution_mode: str = "internal"`
- `Settings` 新增 `sql_execution_mode: str = "internal"`
- `routes.py` lifespan 中透传给 `loader.configure()`

**Step 4: Run tests — expected ALL PASS**

**Step 5: Commit**

```bash
git commit -m "feat(config): add sql_execution_mode setting (internal/external)"
```

---

## 执行顺序

| 顺序 | Task | 预计时间 |
|------|------|---------|
| 1 | Task 1: PlanValidator SQL 字段校验 | 15 min |
| 2 | Task 2: PlanValidator function_id 校验 | 10 min |
| 3 | Task 3: handlers.py 事件处理链 | 10 min |
| 4 | Task 4: MCP tools/call 操作类测试 | 10 min |
| 5 | Task 5: CRM 端到端场景测试 | 20 min |
| 6 | Task 6: sql_execution_mode 切换 | 10 min |
| - | 最终全量测试验证 | 5 min |
