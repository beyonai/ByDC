# ObjectViewFunction 入参出参 + 执行前校验与参数转换 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 扩展 ObjectViewFunction 含 params/description，执行前校验 API 步骤参数，并将逻辑参数转换为物理 API 格式。

**Architecture:** ObjectViewBuilder 从 action 填充 ObjectViewFunction.params；PlanValidator 扩展 API 参数校验；ExecutionObjectConverter 接收 payload，按 mapping_path 转换逻辑参数为物理请求体。

**Tech Stack:** Python 3.12, dataclasses

**Design Doc:** `docs/plans/2026-03-09-object-view-function-param-validation-design.md`

---

## Task 1: ObjectViewFunctionParam 与 ObjectViewFunction 扩展

**Files:**
- Modify: `datacloud-data/src/datacloud_data/plan/models.py`
- Test: `datacloud-data/tests/datacloud_data/test_object_view_builder.py`

**Step 1: 编写失败测试**

在 `test_object_view_builder.py` 中增加断言：payload.objects[0].functions[0] 含 description 和 params，且 params 含 param_code、direction、mapping_path。

**Step 2: 运行测试确认失败**

```bash
cd datacloud-data && pytest tests/datacloud_data/test_object_view_builder.py -v -k "function"
```

**Step 3: 实现**

- 在 models.py 新增 `ObjectViewFunctionParam`（param_code, param_name, param_type, direction, required, mapping_path）
- 修改 `ObjectViewFunction`：增加 description、params 字段
- 在 object_view_builder.py 中，构建 ObjectViewFunction 时从 action 填充 description、params

**Step 4: 运行测试确认通过**

**Step 5: Commit**

```bash
git add src/datacloud_data/plan/models.py src/datacloud_data/plan/object_view_builder.py tests/datacloud_data/test_object_view_builder.py
git commit -m "feat(plan): ObjectViewFunction add params and description from action"
```

---

## Task 2: PlanValidator 扩展 API 步骤参数校验

**Files:**
- Modify: `datacloud-data/src/datacloud_data/plan/plan_validator.py`
- Test: `datacloud-data/tests/datacloud_data/test_plan_validator.py`

**Step 1: 编写失败测试**

测试：API step 缺少 required IN 参数时，validate 返回 errors；step.params 含非法 key 时，validate 返回 errors。

**Step 2: 运行测试确认失败**

**Step 3: 实现**

在 PlanValidator 中新增 `_validate_api_step_params(step, payload)`：
- 从 payload 找到 function_id 对应的 ObjectViewFunction
- 收集 IN 且 required 的 param_code，校验 step.params 包含
- 校验 step.params 的 key 均在 IN params 的 param_code 中

**Step 4: 运行测试确认通过**

**Step 5: Commit**

```bash
git add src/datacloud_data/plan/plan_validator.py tests/datacloud_data/test_plan_validator.py
git commit -m "feat(plan): PlanValidator validate API step params"
```

---

## Task 3: 参数转换逻辑（plan 层纯函数）

**Files:**
- Create: `datacloud-data/src/datacloud_data/plan/param_converter.py`
- Test: `datacloud-data/tests/datacloud_data/test_param_converter.py`

**Step 1: 编写测试**

测试 `map_to_physical(logical_params, in_params)`：给定逻辑 params 和 ObjectViewFunctionParam 列表（direction=IN，含 mapping_path），输出物理请求体。例：`{emp_no: "E001"}` + mapping_path `$.requestBody.sql_param_emp_no` → `{sql_param_emp_no: "E001"}`。

**Step 2: 实现**

在 `param_converter.py` 实现 `map_to_physical(logical_params, in_params)`：遍历 in_params（direction=IN），对每个 param，从 logical_params 取 param_code 对应值（或 default_value），按 mapping_path 提取物理 key（`$.requestBody.xxx` → `xxx`），写入结果 dict。SDK 不依赖 service 包。

**Step 3: 运行测试确认通过**

**Step 4: Commit**

```bash
git add src/datacloud_data/plan/param_converter.py tests/datacloud_data/test_param_converter.py
git commit -m "feat(plan): add param_converter map_to_physical by mapping_path"
```

---

## Task 4: ExecutionObjectConverter 接收 payload 并转换 API 参数

**Files:**
- Modify: `datacloud-data/src/datacloud_data/plan/execution_object_converter.py`
- Modify: `datacloud-data/src/datacloud_data/view.py`
- Modify: `datacloud-data/src/datacloud_data/object.py`（若有相同调用）
- Test: `datacloud-data/tests/datacloud_data/test_execution_object_converter.py`

**Step 1: 编写测试**

测试：convert(plan, payload) 对 API step，若 payload 中对应 function 有 mapping_path，则 ApiExecTask.params 为转换后的物理格式。

**Step 2: 实现**

- ExecutionObjectConverter.convert(plan, payload=None)：payload 可选，兼容旧调用
- 对 API step：从 payload 找到 function_id 对应的 ObjectViewFunction，取其 IN params，调用 param_converter.map_to_physical(step.params, in_params)，将结果写入 ApiExecTask.params
- view.py、object.py：convert(plan) → convert(plan, payload)

**Step 3: 运行测试确认通过**

**Step 4: Commit**

```bash
git add src/datacloud_data/plan/execution_object_converter.py src/datacloud_data/view.py src/datacloud_data/object.py tests/datacloud_data/test_execution_object_converter.py
git commit -m "feat(plan): ExecutionObjectConverter convert API params via mapping_path"
```

---

## Task 5: 更新其余引用与集成测试

**Files:**
- 检查并更新所有使用 `ObjectViewFunction(function_code=...)` 的测试
- 检查 `ExecutionObjectConverter().convert(plan)` 的调用点，传入 payload

**Step 1: 运行全量测试**

```bash
cd datacloud-data && pytest tests/ -v
```

**Step 2: 修复失败用例**

**Step 3: Commit**

```bash
git add -A && git commit -m "chore: update tests for ObjectViewFunction and converter"
```

---

## 执行选项

计划已保存到 `docs/plans/2026-03-09-object-view-function-param-validation-implementation.md`。

1. **Subagent-Driven（本会话）**：按任务逐个执行，任务间做代码审查。
2. **Parallel Session（独立会话）**：在新会话中用 executing-plans 批量执行。

你希望用哪种方式？
