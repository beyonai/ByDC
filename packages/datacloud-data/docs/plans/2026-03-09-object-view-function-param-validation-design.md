# ObjectViewFunction 入参出参 + 执行前校验与参数转换设计

**日期**: 2026-03-09  
**目标**: 1) ObjectViewFunction 补充 params、description；2) 执行前校验 API 步骤参数；3) 将逻辑参数转换为物理 API 格式

---

## 1. 背景

- **object_view_json 的 function** 实际对应 **API 对象的 action**，元数据来自 action
- LLM 生成 PlanStep 时使用逻辑参数名（param_code）
- 执行时需调用真实 function（API），API 可能使用不同物理参数名（mapping_path）
- 执行前需：**校验** 参数完整性 + **转换** 逻辑参数 → 物理请求体

---

## 2. 数据模型扩展

### 2.1 ObjectViewFunctionParam（新增）

```python
@dataclass
class ObjectViewFunctionParam:
    param_code: str
    param_name: str
    param_type: str
    direction: str  # IN / OUT
    required: bool = False
    mapping_path: str = ""  # $.requestBody.xxx 或 $.parameters.xxx，用于转换
    default_value: Any = None  # 可选，转换时缺失则注入
```

### 2.2 ObjectViewFunction（扩展）

```python
@dataclass
class ObjectViewFunction:
    function_code: str
    description: str = ""
    params: list[ObjectViewFunctionParam] = field(default_factory=list)
```

### 2.3 ObjectViewBuilder 构建逻辑

对每个 action 的每个 function_ref，创建 ObjectViewFunction：

- `function_code` = function_ref
- `description` = action.description
- `params` = 将 action.params 转为 ObjectViewFunctionParam（含 mapping_path）

---

## 3. 执行前校验（PlanValidator 扩展）

对 type=API 的 step，新增校验：

1. **必填校验**：step.params 必须包含所有 direction=IN 且 required=True 的 param_code
2. **非法参数校验**：step.params 的 key 必须在对应 ObjectViewFunction 的 IN params 中存在
3. **类型提示**（可选）：可记录 param_type 供后续扩展

**实现**：在 `_validate_function_ids` 或新增 `_validate_api_step_params` 中，根据 payload 找到 function_id 对应的 ObjectViewFunction，校验 step.params。

---

## 4. 参数转换（ExecutionObjectConverter 扩展）

### 4.1 输入输出

- **输入**：PlanStep（step.params 为逻辑参数，如 `{userIds: ["x"], names: []}`）
- **输出**：ApiExecTask.params 为物理 API 请求体（如 `{userIds: ["x"]}` 或 `{sql_param_emp_no: "xxx"}`）

### 4.2 转换规则

根据 mapping_path 将逻辑参数写入物理位置：

| mapping_path 模式 | 目标位置 | 示例 |
|------------------|----------|------|
| `$.requestBody.xxx` | 请求体 JSON 的 key `xxx` | `{emp_no: "E001"}` + `$.requestBody.sql_param_emp_no` → `{sql_param_emp_no: "E001"}` |
| `$.parameters.xxx` | 查询参数或 path 参数 | 暂支持合并到 requestBody（与现有 ApiExecutor 兼容），后续可扩展 |

**简化实现**：提取 mapping_path 最后一节作为物理 key（如 `$.requestBody.userIds` → `userIds`），构建 `{physical_key: value}`。若多个 IN 参数，合并到同一 dict。

### 4.3 依赖

- ExecutionObjectConverter 需要 **payload** 才能找到 function_id 对应的 params 及 mapping_path
- 接口变更：`convert(plan, payload)` 或 `convert(plan, payload=...)`

### 4.4 默认值

若 step.params 缺少某 IN 参数且该参数有 default_value，转换时注入 default_value。

---

## 5. 调用链变更

```
View.query:
  ...
  PlanValidator().validate(plan, payload)     # 扩展：API 步骤参数校验
  ...
  ExecutionObjectConverter().convert(plan, payload)  # 扩展：API 步骤参数转换
  executor.run(tasks)
```

---

## 6. 错误处理

- **校验失败**：返回 ValidationResult.errors，触发 LLM 重试
- **转换失败**：若 mapping_path 无法解析或缺少必填参数，抛出明确异常，不执行

---

## 7. 改动文件清单

| 文件 | 改动 |
|------|------|
| `plan/models.py` | 新增 ObjectViewFunctionParam；ObjectViewFunction 增加 description、params |
| `plan/object_view_builder.py` | 构建 ObjectViewFunction 时填充 description、params（含 mapping_path） |
| `plan/plan_validator.py` | 扩展 API 步骤参数校验 |
| `plan/execution_object_converter.py` | 接收 payload；API 步骤参数转换 |
| `view.py` / `object.py` | convert(plan) → convert(plan, payload) |
| `tests/` | 相应单测更新 |

---

## 8. 与 ApiExecutor 的衔接

ApiExecutor 当前：`client.post(url, json=task.params)`。转换后的 ApiExecTask.params 已是物理格式，无需改动 ApiExecutor。

响应提取（`_extract_records`）可后续按 OUT 参数的 mapping_path 增强，本期不涉及。
