# 术语绑定与 API 参数绑定 - 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 实现术语参数转换（API + SQL 执行时）及 API 步骤 bind 能力，使模型可输出名称/标签，系统在执行前解析为 ID/code。

**Architecture:** 在 ExecutionObjectConverter 中接入 TermResolver，对 API 步骤先 bind 注入、再术语解析、再 map_to_physical；对 SQL 步骤支持 params 占位符并做术语解析后替换。ApiExecutor 支持 bind_from_step/bind_key 从前序 CSV 取列值注入 params。

**Tech Stack:** Python, dataclasses, TermLoader, TermResolver

**参考设计:** `docs/plans/2026-03-09-term-binding-and-api-bind-design.md`

---

## Task 1: ObjectViewFunctionParam 增加 term_set

**Files:**
- Modify: `datacloud-data-service/src/datacloud_data_sdk/plan/models.py`
- Modify: `datacloud-data-service/src/datacloud_data_sdk/plan/object_view_builder.py`
- Test: `datacloud-data-service/tests/datacloud_data_sdk/test_plan_models.py`（若无则新建）

**Step 1: 编写失败测试**

```python
def test_object_view_function_param_has_term_set():
    from datacloud_data_sdk.plan.models import ObjectViewFunctionParam
    p = ObjectViewFunctionParam(
        param_code="orgId",
        param_name="组织",
        param_type="STRING",
        direction="IN",
        term_set="org.code",
    )
    assert p.term_set == "org.code"
```

**Step 2: 运行测试确认失败**

Run: `pytest datacloud-data-service/tests/datacloud_data_sdk/test_plan_models.py::test_object_view_function_param_has_term_set -v`
Expected: FAIL (ObjectViewFunctionParam 无 term_set 参数)

**Step 3: 实现**

在 `ObjectViewFunctionParam` 中增加 `term_set: str | None = None`。

**Step 4: 运行测试确认通过**

**Step 5: ObjectViewBuilder 传入 term_set**

在 `object_view_builder.py` 中，从 `a.params` 构建 `ObjectViewFunctionParam` 时传入 `term_set=p.term_set`（需从 OntologyActionParam 取，ontology 已有该字段）。

**Step 6: Commit**

```bash
git add -A && git commit -m "feat(plan): ObjectViewFunctionParam add term_set, ObjectViewBuilder pass from ontology"
```

---

## Task 2: ObjectViewField 增加 term_set

**Files:**
- Modify: `datacloud-data-service/src/datacloud_data_sdk/plan/models.py`
- Modify: `datacloud-data-service/src/datacloud_data_sdk/plan/object_view_builder.py`

**Step 1:** 在 `ObjectViewField` 中增加 `term_set: str | None = None`。

**Step 2:** 在 ObjectViewBuilder 构建 fields 时，从 `OntologyField` 传入 `term_set=f.term_set`。

**Step 3:** Commit

```bash
git commit -m "feat(plan): ObjectViewField add term_set for SQL term resolution"
```

---

## Task 3: ApiExecTask 增加 bind_from_step、bind_key

**Files:**
- Modify: `datacloud-data-service/src/datacloud_data_sdk/executor/models.py`
- Test: `datacloud-data-service/tests/datacloud_data_sdk/test_execution_object_converter.py`

**Step 1: 编写测试**

```python
def test_api_exec_task_has_bind_fields():
    from datacloud_data_sdk.executor.models import ApiExecTask
    t = ApiExecTask(
        function_code="fn_x",
        params={},
        bind_from_step="s1",
        bind_key="orgId",
    )
    assert t.bind_from_step == "s1"
    assert t.bind_key == "orgId"
```

**Step 2:** 在 `ApiExecTask` 中增加 `bind_from_step: str = ""`、`bind_key: str = ""`。

**Step 3:** 在 `ExecutionObjectConverter._convert_step` 的 API 分支中，将 `step.bind_from_step`、`step.bind_key` 传入 `ApiExecTask`。

**Step 4:** Commit

```bash
git commit -m "feat(executor): ApiExecTask add bind_from_step, bind_key"
```

---

## Task 4: TermResolver 新增 resolve_params（SDK 层）

**依赖关系**：`datacloud_data_sdk` 为核心库，`datacloud_data_service` 依赖 sdk。TermResolver 需在 sdk 中供 ExecutionObjectConverter 使用。在 sdk 中新增 `plan/term_resolver.py`，service 层的 `term_resolver` 可改为 import 并复用。

**Files:**
- Create: `datacloud-data-service/src/datacloud_data_sdk/plan/term_resolver.py`
- Modify: `datacloud-data-service/src/datacloud_data_service/tools/term_resolver.py`（改为 import sdk 的 TermResolver 并复用 resolve）
- Test: `datacloud-data-service/tests/datacloud_data_sdk/test_term_resolver.py`

**Step 1: 编写失败测试**

```python
def test_resolve_params_enum():
    from datacloud_data_sdk.ontology.term_loader import TermLoader
    from datacloud_data_sdk.plan.term_resolver import TermResolver
    from datacloud_data_sdk.plan.models import ObjectViewFunctionParam

    loader = TermLoader.from_mapping({
        "status.code": [
            {"code": "TODO", "label": "待办"},
            {"code": "DONE", "label": "已完成"},
        ],
    })
    resolver = TermResolver(loader)
    specs = [
        ObjectViewFunctionParam("status", "状态", "STRING", "IN", term_set="status.code"),
    ]
    result = resolver.resolve_params({"status": "待办"}, specs)
    assert result["status"] == "TODO"
```

**Step 2:** 运行测试确认失败（模块/方法不存在）

**Step 3: 实现 sdk/plan/term_resolver.py**

```python
"""TermResolver: 术语标签/名称 → 标准 code 转换。"""
from __future__ import annotations
from typing import Any, TYPE_CHECKING
if TYPE_CHECKING:
    from datacloud_data_sdk.plan.models import ObjectViewFunctionParam
from datacloud_data_sdk.ontology.term_loader import TermLoader

class TermResolver:
    def __init__(self, term_loader: TermLoader | None = None) -> None:
        self._term_loader = term_loader

    def resolve_params(
        self,
        params: dict[str, Any],
        param_specs: list["ObjectViewFunctionParam"],
    ) -> dict[str, Any]:
        """对含 term_set 的参数做名称/标签→code 解析。"""
        if not self._term_loader:
            return params
        resolved = dict(params)
        for p in param_specs:
            if getattr(p, "term_set", None) and p.param_code in resolved:
                try:
                    resolved[p.param_code] = self._term_loader.resolve_code(
                        p.term_set, str(resolved[p.param_code])
                    )
                except ValueError:
                    pass
        return resolved
```

**Step 4:** 运行测试确认通过

**Step 5:** 更新 service 层 term_resolver，使其 import sdk 的 TermResolver 并继承或组合，保留原有 `resolve(action, params)` 供 action_executor 使用。

**Step 6:** Commit

```bash
git commit -m "feat(plan): TermResolver in sdk with resolve_params for ObjectViewFunctionParam"
```

---

## Task 5: ExecutionObjectConverter 接入 TermResolver（API 步骤）

**Files:**
- Modify: `datacloud-data-service/src/datacloud_data_sdk/plan/execution_object_converter.py`
- Modify: `datacloud-data-service/src/datacloud_data_sdk/view.py`
- Modify: `datacloud-data-service/src/datacloud_data_sdk/object.py`

**Step 1:** ExecutionObjectConverter 构造函数接受 `term_resolver: TermResolver | None = None`。

**Step 2:** 在 API 步骤转换逻辑中：
- 先 `term_resolver.resolve_params(step.params, in_params)` 得到 resolved_params
- 再 `map_to_physical(resolved_params, in_params)` 得到物理 params
- 若 `term_resolver` 为 None，则跳过 resolve，直接 map_to_physical。

**Step 3:** View.query / Object.query 中构建 ExecutionObjectConverter 时传入 term_resolver。term_resolver 需要 TermLoader，TermLoader 需从 LoaderConfig 或 OntologyLoader 获取。检查 OntologyLoader 是否已有 term_loader；若无，则从 ontology 的 terms 配置或 `resources/ontology/<domain>/terms.json` 加载。

**Step 4:** 若 LoaderConfig 无 term_loader，则传入 None，保持向后兼容。

**Step 5:** 编写/更新测试：convert(plan, payload) 且 payload 中 function 的 param 有 term_set 时，params 被正确解析。

**Step 6:** Commit

```bash
git commit -m "feat(plan): ExecutionObjectConverter term resolution for API steps"
```

---

## Task 6: ApiExecutor 支持 bind_from_step / bind_key

**Files:**
- Modify: `datacloud-data-service/src/datacloud_data_sdk/executor/api_executor.py`
- Modify: `datacloud-data-service/src/datacloud_data_sdk/executor/executor.py`

**Step 1:** ApiExecutor.execute 签名增加 `step_results: dict[str, str]` 参数（与 SqlExecutor 一致，便于 Executor 传入）。

**Step 2:** 在 execute 内，若 task 有 bind_from_step、bind_key：
- 从 step_results[bind_from_step] 读取 CSV
- 取 bind_key 列的值（单值取第一行，多值按业务约定，先实现单值）
- 注入到 params 的对应 key（需与 function 的 IN 参数对应，如 orgId）

**Step 3:** Executor.run 中调用 api_executor.execute 时传入 step_results。

**Step 4:** 编写测试：bind 场景下 params 被正确注入。

**Step 5:** Commit

```bash
git commit -m "feat(executor): ApiExecutor support bind_from_step, bind_key"
```

---

## Task 7: 序列化 object_view 时拆分为 inputParams/outputParams 并注入 termType/termLabels/termHint

**Files:**
- Modify: `datacloud-data-service/src/datacloud_data_sdk/plan/query_plan_generator.py`（或独立序列化模块）
- 需接入 TermLoader 以判断 enum/lookup 并注入 termLabels 或 termHint

**Step 1:** 在 `_serialize_payload` 或新增 `_serialize_function_for_llm` 中：
- 将 function.params 按 direction 拆为 inputParams、outputParams
- 对每个 inputParam 若有 term_set：
  - 调用 `term_loader.get_available_values(term_set)`，若非空 → termType: "enum", termLabels: [...]
  - 若空 → termType: "lookup", termHint: "接受名称或ID，系统会解析"
- 输出 paramCode, paramName, paramType, required, termSet, termType, termLabels/termHint

**Step 2:** 需将 TermLoader 传入 QueryPlanGenerator 或 ObjectViewBuilder 的序列化逻辑。View/Object 的 query 流程中，payload 由 ObjectViewBuilder 构建，序列化在 QueryPlanGenerator 的 user_message 中。因此需在生成 payload 后、传给 LLM 前，对 payload 做「序列化增强」。可在 `_serialize_payload` 中接收 `term_loader: TermLoader | None`，对 functions 的 params 做上述处理。

**Step 3:** LangGraphPlanGenerator 调用 _serialize_payload 时传入 config 中的 term_loader。

**Step 4:** 编写测试：序列化后的 JSON 包含 inputParams、outputParams，且带 termSet 的 param 有 termType、termLabels 或 termHint。

**Step 5:** Commit

```bash
git commit -m "feat(plan): serialize object_view with inputParams/outputParams and termType/termLabels/termHint"
```

---

## Task 8: Prompt 增加 function 结构说明、termSet、优先单步、bind 说明

**Files:**
- Modify: `datacloud-data-service/src/datacloud_data_sdk/plan/query_plan_generator.py`（SYSTEM_PROMPT）

**Step 1:** 在 SYSTEM_PROMPT 的「输出要求」之前插入「对象视图中的 function 结构说明」段落，内容与 `docs/plans/2026-03-09-prompt-and-json-example-for-test.md` 第一节一致，包括：
- inputParams / outputParams
- termType: enum → termLabels
- termType: lookup / termHint
- 优先单步
- bindFromStep / bindKey

**Step 2:** 同时更新 API 步骤的 steps 说明，提及 bindFromStep、bindKey。

**Step 3:** Commit

```bash
git commit -m "feat(plan): SYSTEM_PROMPT add function structure, termSet, single-step priority, bind"
```

---

## Task 9: SQL 步骤术语参数转换

**设计**：SQL 步骤支持可选 `params` 与占位符。模型输出 `sqlTemplate: "SELECT * FROM t WHERE status = {status}"` 且 `params: {status: "待办"}` 时，执行前解析 params 中的术语值并替换到 sql_template。

**Files:**
- Modify: `datacloud-data-service/src/datacloud_data_sdk/plan/models.py`（PlanStep 的 SQL 已有 sql_template，需支持 params）
- Modify: `datacloud-data-service/src/datacloud_data_sdk/executor/models.py`（SqlExecTask 增加 params 或 resolved_sql）
- Modify: `datacloud-data-service/src/datacloud_data_sdk/plan/execution_object_converter.py`
- Modify: `datacloud-data-service/src/datacloud_data_sdk/sql_executor/sql_executor.py`

**Step 1:** PlanStep 已有 params 字段（通用）。确认 LLM 解析时 SQL 步骤可包含 params。

**Step 2:** SqlExecTask 增加 `params: dict[str, Any] = field(default_factory=dict)`。ExecutionObjectConverter 转换 SQL 步骤时：
- 若 step.params 非空且 payload 可用，根据 object view 的 fields（按 param 名匹配）获取 term_set，调用 term_resolver.resolve_params
- 将解析后的值替换 sql_template 中的 `{param_name}` 占位符（注意 SQL 字符串需加引号）
- 得到最终 sql 传入 SqlExecTask；或 SqlExecTask 保留 sql_template 与 params，由 SqlExecutor 在执行时替换。

**Step 3:** 为简化，在 ExecutionObjectConverter 中完成解析与替换，SqlExecTask 只接收最终 sql_template（已替换后的 SQL 字符串）。这样 SqlExecutor 无需改动。

**Step 4:** 实现逻辑：
- 对 SQL step，若 step.params 非空：
  - 构建 param_specs：从 payload.objects[].fields 中，对每个 param key 找到对应 field，若有 term_set 则加入 ObjectViewFunctionParam 风格的 spec（可复用或新建轻量结构）
  - term_resolver.resolve_params(step.params, param_specs)
  - 对 sql_template 中每个 `{k}` 用 `resolved[k]` 替换，字符串类型加引号
- 若 step.params 为空，sql_template 不变。

**Step 5:** Prompt 中补充：当 SQL 条件涉及带 term_set 的字段时，使用占位符 `{field_name}` 并在 params 中填写标签/名称，系统会解析。

**Step 6:** 编写测试：SQL 步骤带 params 且 field 有 term_set 时，最终 sql 中为 code 而非 label。

**Step 7:** Commit

```bash
git commit -m "feat(plan): SQL step term resolution via params placeholder"
```

---

## Task 10: Lookup 类型术语解析（可选 / 后续）

**说明**：termType: lookup 时，若 TermLoader 中无对应 term_set 数据，需通过外部服务解析名称→ID。设计文档未规定具体实现。本任务可留作后续：

- 定义 `LookupResolver` 接口：`resolve(term_set: str, value: str) -> str`
- 当 term_loader.get_available_values 为空时，若配置了 lookup_resolver，则调用
- 默认无 lookup_resolver 时，对 lookup 类型 pass-through（原样传递），由下游 API 自行处理

---

## Task 11: 集成测试与文档

**Files:**
- Test: `datacloud-data-service/tests/datacloud_data_sdk/test_term_binding_e2e.py`（可选）
- Modify: `docs/plans/2026-03-09-prompt-and-json-example-for-test.md`（若需）

**Step 1:** 编写端到端测试：objectView 含 term_set 的 function，用户问题含名称，计划输出名称，执行后 API 收到 code。

**Step 2:** 更新设计文档的「验收标准」检查清单，逐项验证。

**Step 3:** Commit

```bash
git commit -m "test: e2e term binding and api bind"
```

---

## 执行选项

计划已保存至 `docs/plans/2026-03-09-term-binding-and-api-bind-implementation.md`。

**两种执行方式：**

1. **Subagent-Driven（本会话）**：按任务分派子 agent，每任务后审查，快速迭代  
2. **Parallel Session（新会话）**：在新会话中用 executing-plans，按检查点批量执行  

**选择哪种方式？**
