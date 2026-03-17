# 术语转换执行前检查清单（调试用）

**日期**: 2026-03-09  
**目的**: 排查「执行前未走到术语转换逻辑」的问题。

---

## 1. 术语转换发生位置

术语转换在 **ExecutionObjectConverter._convert_step** 中，当 `step.type == "API"` 时：

```python
# execution_object_converter.py 第 46-55 行
if payload and step.function_id:
    fn = self._find_function(step.function_id, payload)
    if fn:
        in_params = [p for p in fn.params if p.direction == "IN"]
        if self._term_resolver and in_params:
            params = self._term_resolver.resolve_params(step.params, in_params)
        params = map_to_physical(params, in_params)
```

**必须同时满足**：
1. `payload` 不为 None
2. `step.function_id` 非空
3. `_find_function(step.function_id, payload)` 返回非 None
4. `in_params` 非空（该 function 有 IN 方向参数）
5. `self._term_resolver` 不为 None

---

## 2. term_resolver 创建条件

在 **view.py** 第 188-192 行：

```python
term_resolver = None
if getattr(config, "term_loader", None):
    term_resolver = TermResolver(config.term_loader)
tasks = ExecutionObjectConverter(term_resolver=term_resolver).convert(plan, payload)
```

**条件**：`config.term_loader` 必须存在。

---

## 3. term_loader 配置条件

在 **routes.py** 第 128-134 行：

```python
if settings.znt_server:
    term_loader = TermLoader()
    term_loader.configure_api(settings.znt_server)
    loader.configure(term_loader=term_loader)
```

**条件**：环境变量 `DC_ZNT_SERVER` 必须配置且非空。

---

## 4. 诊断检查点（按优先级）

### 4.1 是否配置了 DC_ZNT_SERVER？

- **检查**：`.env` 或环境变量中是否有 `DC_ZNT_SERVER=https://...`
- **现象**：未配置时 `term_loader` 为 None，`term_resolver` 为 None，**永远不会执行术语转换**
- **解决**：在 `.env` 中增加 `DC_ZNT_SERVER`（即使术语 API 暂不可用，也可先配置占位地址，用于验证流程）

### 4.2 _find_function 是否找到 function？

- **检查**：`step.function_id` 与 `payload.objects[].functions[].function_code` 是否一致
- **可能原因**：
  - LLM 返回的 `functionId` 与本体中 `function_refs` 不一致
  - 使用 scene 时，scene 的 `object_ids` 与 plan 使用的 function 所属对象不一致
  - payload 的 objects 来自 ObjectViewBuilder，其 functions 来自 ontology 的 actions.function_refs
- **调试**：在 `ExecutionObjectConverter._convert_step` 中加日志：
  ```python
  fn = self._find_function(step.function_id, payload)
  if not fn:
      logger.warning("_find_function returned None: function_id=%s", step.function_id)
  ```

### 4.3 该 function 是否有 IN 参数？

- **检查**：`in_params = [p for p in fn.params if p.direction == "IN"]` 是否非空
- **现象**：若该 API 的 params 全是 OUT，`in_params` 为空，不会调用 `resolve_params`
- **说明**：术语转换只对 IN 参数生效（用户填写的入参需要名称→code 解析）

### 4.4 payload 是否传入？

- **检查**：`ExecutionObjectConverter.convert(plan, payload)` 调用时 `payload` 是否为 None
- **来源**：view.query 中 `payload = builder.build(object_ids=...)`，一定会传
- **说明**：正常流程下 payload 不应为 None

### 4.5 Object.query 是否同样配置？

- **说明**：`object.py` 中也有相同逻辑（第 217-222 行），单对象查询时同样依赖 `config.term_loader`
- **检查**：若通过 Object.query 调用，同样需确保 `DC_ZNT_SERVER` 已配置

---

## 5. 建议的调试步骤

1. **确认 DC_ZNT_SERVER**：在 `.env` 中设置 `DC_ZNT_SERVER=https://your-term-server`，重启服务，查看启动日志是否有 `Configured TermLoader with znt_server=...`
2. **加断点/日志**：在 `ExecutionObjectConverter._convert_step` 的 API 分支（约第 46 行）加日志，打印 `payload is not None`、`step.function_id`、`fn is not None`、`len(in_params)`、`term_resolver is not None`
3. **验证 function 匹配**：打印 payload 中所有 `function_code`，与 `step.function_id` 对比

---

## 6. 数据流简图

```
View.query(question)
  → builder.build() → payload
  → plan_generator.generate(payload, term_loader) → plan
  → term_resolver = TermResolver(config.term_loader)  # 若 term_loader 存在
  → ExecutionObjectConverter(term_resolver).convert(plan, payload)
      → 对每个 API step:
          fn = _find_function(step.function_id, payload)
          if fn and term_resolver and in_params:
              params = term_resolver.resolve_params(step.params, in_params)
  → ApiExecutor.execute(task)  # task.params 已是解析后的值
```

---

## 7. 快速验证：无 API 时的 fallback

若暂时无法配置真实术语 API，可：

1. 使用 **内存 TermLoader**：在 routes 中创建 `TermLoader.from_mapping({...})` 并 `loader.configure(term_loader=...)`，不依赖 DC_ZNT_SERVER
2. 或保留 `DC_ZNT_SERVER` 配置：TermLoader 会尝试调用 API，失败时返回空列表，但 `term_resolver` 会存在，`resolve_params` 会执行（只是 TermLoader.resolve_code 可能因无数据而抛错）
