# 术语绑定（名称→ID 转换）与 API 步骤参数绑定设计

**日期**: 2026-03-09  
**目标**: 1) 当对象属性或动作参数绑定术语且为「名称」类型时，模型识别为名称、执行时转为 ID；2) API 步骤支持从前序步骤结果绑定参数（bind_from_step / bind_key）；3) 对象视图对模型更易理解（出入参分离、术语知识透传）

---

## 1. 背景

### 1.1 术语绑定与名称→ID 转换

- 本体中 action 的 params 可声明 `term_set`（如 `org.name`、`user.name`、`status.code`）
- `term_set` 为「名称」类型（如 `*.name`）时：用户/模型使用**名称**，API 需要 **ID/code**
- 需要：模型在计划中输出名称 → 执行前由系统将名称解析为 ID
- **约束**：所有逻辑基于 `term_set` 字符串，禁止在代码中写死具体领域（如「组织」「org」）

### 1.2 API 步骤参数绑定与优先单步

- **优先单步**：当目标 API 的入参有 term_set（lookup）时，模型可直接填名称，系统解析为 ID，无需先调用「按名称查某实体」再 bind。例如「查询某部门销售人员的数量」→ 直接用 `fn_po_users_query_by_org`，params.orgId: "营销一部"。
- **bind 场景**：仅当目标 API 入参无 term_set、或需从前序步骤取多行数据时，才用 bind。例如 Step1 查组织列表 → Step2 按每个 orgId 查人员。
- 当前：`PlanStep` 已有 `bind_from_step`、`bind_key`，但 `ApiExecTask` 无此字段，`ApiExecutor` 不从前序步骤取数注入 params

### 1.3 模型可理解性

- 当前 function 的 params 为扁平列表，IN/OUT 混在一起，模型不易区分「需填写的入参」与「返回的出参」
- 术语绑定后，模型需要知道：该参数接受什么值、是否支持名称/ID 双写

---

## 2. 数据模型扩展

### 2.1 ObjectViewFunction：出入参分离

**现状**：`params` 为扁平列表，含 IN 与 OUT。

**调整**：在序列化给模型的 object_view_json 中，将 params 拆分为 `inputParams`、`outputParams`：

```json
{
  "functionCode": "fn_xxx",
  "description": "...",
  "inputParams": [...],
  "outputParams": [...]
}
```

- `inputParams`：direction=IN 的参数，模型需在 step.params 中填写
- `outputParams`：direction=OUT 的参数，供模型理解返回结构、用于后续步骤 bind 或聚合

**实现**：`ObjectViewFunction` 仍保留 `params` 列表（内部使用）；序列化时由 `_serialize_payload` 或新增 `_serialize_function_for_llm` 生成 `inputParams`/`outputParams`。

### 2.2 ObjectViewFunctionParam（扩展）

```python
@dataclass
class ObjectViewFunctionParam:
    param_code: str
    param_name: str
    param_type: str
    direction: str
    required: bool = False
    mapping_path: str = ""
    default_value: Any = None
    term_set: str | None = None  # 新增：如 org.name, user.name, org.code
```

### 2.3 ApiExecTask（扩展）

```python
@dataclass
class ApiExecTask:
    function_code: str
    params: dict[str, Any] = field(default_factory=dict)
    output_ref: str = ""
    csv_table_name: str = ""
    bind_from_step: str = ""
    bind_key: str = ""
```

### 2.4 ObjectViewBuilder 构建逻辑

- 从 `action.params` 构建 `ObjectViewFunctionParam` 时，传入 `term_set=p.term_set`

---

## 3. 术语绑定与名称→ID 转换

### 3.1 术语知识透传给模型

根据术语类型，向模型提供不同信息（**不写死任何领域名**）：

| 术语类型 | 说明 | 给模型的信息 |
|----------|------|--------------|
| **枚举（dict）** | 固定值集（如 status.code、priority.code、approvalStatus.code） | 必须提供 `termLabels: ["标签1","标签2",...]`，模型**只能**从这些值中选，否则会识别错 |
| **查找（list）** | 动态列表，绑定名称（如 `*.name`） | 提供 `termHint`：`"该参数接受名称或ID，系统会在执行时解析"`，不提供具体数据 |

**枚举数据来源与注入逻辑**：

1. **数据来源**：TermLoader 从 terms 配置加载（格式：`{term_set: [{code, label, aliases?}]}`）。terms 可来自：
   - 独立文件：`resources/ontology/<domain>/terms.json`
   - 或 ontology 根节点的 `terms` 字段
2. **判断规则**（基于数据可用性，非硬编码）：
   - 调用 `term_loader.get_available_values(term_set)`，若返回非空列表 → **枚举**，透传 `termType: "enum"`, `termLabels: [...]`
   - 若返回空或 term_set 不存在 → **查找**，透传 `termType: "lookup"`, `termHint: "接受名称或ID，系统会解析"`
3. **对象字段**：若 object 的 field 也有 `term_set`（如 reportStatus.code），序列化时同样注入 `termLabels` 或 `termHint`，供模型在 SQL 条件、KB tags 等场景使用。

**序列化示例**（入参带术语）：

```json
{
  "paramCode": "orgId",
  "paramName": "组织",
  "paramType": "STRING",
  "required": true,
  "termSet": "org.code",
  "termType": "lookup",
  "termHint": "接受名称或ID，系统会解析"
}
```

```json
{
  "paramCode": "status",
  "paramName": "状态",
  "paramType": "STRING",
  "required": true,
  "termSet": "status.code",
  "termType": "enum",
  "termLabels": ["待办", "进行中", "已完成", "已取消"]
}
```

**terms 配置示例**（`resources/ontology/crm_demo/terms.json`）：

```json
{
  "status.code": [
    {"code": "TODO", "label": "待办"},
    {"code": "IN_PROGRESS", "label": "进行中"},
    {"code": "DONE", "label": "已完成"},
    {"code": "CANCELLED", "label": "已取消"}
  ],
  "priority.code": [
    {"code": "HIGH", "label": "高"},
    {"code": "MEDIUM", "label": "中"},
    {"code": "LOW", "label": "低"}
  ],
  "approvalStatus.code": [
    {"code": "PENDING", "label": "待审批"},
    {"code": "APPROVED", "label": "已通过"},
    {"code": "REJECTED", "label": "已驳回"}
  ]
}
```

### 3.2 模型侧（Prompt）

在 SYSTEM_PROMPT 中增加（**示例用占位符，不写死 org**）：

- function 的 `inputParams` 为模型需要填写的入参；`outputParams` 为返回结构说明
- 当入参有 `termSet` 时：
  - `termType: "enum"`：从 `termLabels` 或 `termEntries` 中选取合法值
  - `termType: "lookup"` 或 `termHint` 存在：可填名称或 ID，系统会解析
- **优先单步**：当目标 API 的入参已有 termSet（termType: lookup）且能接受用户问题中的名称时，**直接在 params 中填写该名称**，无需先调用其他 API 获取 ID。系统会在执行时解析。优先使用单步查询，避免不必要的多步链式调用（如无需先查「按名称查某实体」再 bind）。
- 所有说明均基于 `termSet`、`termType` 等元数据，不依赖具体领域名

### 3.3 执行侧（TermResolver 接入）

**扩展 TermResolver**：支持基于 `ObjectViewFunctionParam` 列表解析，而非仅 `OntologyAction`：

```python
def resolve_params(
    self,
    params: dict[str, Any],
    param_specs: list[ObjectViewFunctionParam],
) -> dict[str, Any]:
    """对含 term_set 的参数做名称/标签→code 解析。"""
```

**调用时机**：在 `ExecutionObjectConverter` 中，对 API 步骤：

1. 先 `term_resolver.resolve_params(step.params, in_params)` 得到解析后 params
2. 再 `map_to_physical(resolved_params, in_params)` 得到物理请求体

**TermLoader 来源**：由 `LoaderConfig` 或 `OntologyLoader` 提供（可从 ontology 的 terms 配置或独立 terms 文件加载）。若未配置，跳过术语解析。

### 3.4 错误处理

- 术语解析失败（名称不在术语集中）：抛出明确异常，包含可用值提示
- 可选：在 PlanValidator 中预校验「名称是否在术语集中」，提前发现错误并触发重试

---

## 4. API 步骤参数绑定（bind）

### 4.1 ExecutionObjectConverter

- 对 API 步骤，若 `step.bind_from_step`、`step.bind_key` 非空，在构建 `ApiExecTask` 时传入
- 不在 converter 中解析 bind 值（由 ApiExecutor 在执行时解析）

### 4.2 ApiExecutor

- 执行前：若 task 有 `bind_from_step`、`bind_key`，从 `step_results[bind_from_step]` 的 CSV 中取 `bind_key` 列的值
- 注入方式：
  - 若为单值：注入到 `params` 对应 key（需与 function 的 IN 参数对应，如 `orgId`）
  - 若为多行：按业务约定（如取第一行、或批量查询）
- 与 `term_resolver` 的关系：bind 注入在术语解析**之前**，即先注入再解析（若注入的值为名称，会一并解析）

### 4.3 Prompt 说明

在 SYSTEM_PROMPT 中增加多步 API 链式调用说明：

- 当后续 API 步骤需要前序步骤的某列数据时，使用 `bindFromStep`（前序 stepId）、`bindKey`（列名）
- 示例：Step1 查得某 ID 列，Step2 的对应参数可设为 `bindFromStep: "s1"`, `bindKey: "列名"`（列名来自前序 outputParams）

---

## 5. 数据流

**推荐（单步）**：当 `fn_po_users_query_by_org` 的 orgId 参数有 term_set 时，模型可直接填名称，无需先查组织：

```
用户问题：「查询某部门销售人员的数量」
    ↓
Plan: Step1 API(fn_po_users_query_by_org) params={orgId:"营销一部"}
      Step2 SQLITE_MEM 聚合（或 DIRECT 若仅需计数）
    ↓
ExecutionObjectConverter: term_resolve({orgId:"营销一部"}) → {orgId:"org_123"}
    map_to_physical → 物理请求体
    ↓
ApiExecutor 执行
```

**备选（多步）**：当目标 API 的入参**无** term_set、或需从前序步骤取**多行**数据时，才使用 bind：

```
Plan: Step1 API(查某实体) params={...} csvTableName=xxx
      Step2 API(按前序列查) bindFromStep=s1, bindKey=yyy
      ...
```

**注意**：优先单步；仅当目标 API 无法直接接受名称（且无 term_set）或需批量 bind 时，才用多步链式调用。

**本体要求**：为使「查询某部门人员」可单步完成，`fn_po_users_query_by_org` 的 orgId 入参需声明 `term_set: org.code`（或 org.name），以便模型填名称、系统解析。若 ontology 中该 param 无 term_set，需补充。

---

## 6. 改动文件清单

| 文件 | 改动 |
|------|------|
| `plan/models.py` | ObjectViewFunctionParam 增加 term_set；ApiExecTask 增加 bind_from_step、bind_key |
| `plan/object_view_builder.py` | 构建 param 时传入 term_set |
| `plan/query_plan_generator.py` | Prompt 增加 inputParams/outputParams、termSet/termType/termHint/termLabels、bind 说明 |
| `plan/execution_object_converter.py` | API 步骤：先 term_resolve 再 map_to_physical；传入 bind 字段 |
| `plan/` 序列化逻辑 | 序列化 object_view 时：params 拆为 inputParams/outputParams；为带 term_set 的 param 注入 termType、termLabels/termHint（需 TermLoader） |
| `executor/models.py` | ApiExecTask 增加 bind_from_step、bind_key |
| `executor/api_executor.py` | 执行前从 step_results 解析 bind，注入 params |
| `tools/term_resolver.py` | 新增 resolve_params(params, param_specs) |
| `ontology/loader.py` 或 `config` | 提供 TermLoader（可选，具体见实现计划） |
| `view.py` | 若 ExecutionObjectConverter 需要 term_loader，需传入 |
| `tests/` | 相应单测与场景测试 |

---

## 7. 与现有能力的衔接

- **ObjectViewFunctionParam 校验**：已有 required、非法 key 校验，不变
- **param_converter.map_to_physical**：输入为术语解析后的逻辑 params，输出为物理请求体，不变
- **TermResolver**：现有 `resolve(action, params)` 供 action_executor 使用；新增 `resolve_params(params, param_specs)` 供查询流水线使用

---

## 8. 验收标准

1. 对象视图的 function 对模型呈现为 `inputParams`/`outputParams`，模型能正确区分入参与出参
2. 枚举类 term_set：模型能获得 termLabels/termEntries，从合法值中选
3. 查找类 term_set（*.name）：模型能获得 termHint，知道可填名称或 ID
4. 参数声明了 term_set 时，模型在计划中输出名称，执行时系统解析为 ID
5. API 步骤可使用 `bindFromStep`、`bindKey` 从前序步骤 CSV 取列值注入 params
6. 代码中无对「org」「组织」等具体领域的硬编码
