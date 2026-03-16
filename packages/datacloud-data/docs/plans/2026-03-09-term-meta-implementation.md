# termMeta 转换与术语 API 加载 - 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 本体 JSON 的 termMeta 转换为 term_set、term_type、dataset_id，并支持通过术语 API 加载术语数据。

**Architecture:** 在 OntologyLoader 解析时从 termMeta 推导 term_set/term_type/dataset_id；模型增加 term_type、dataset_id；TermLoader 扩展支持 API 模式，调用 POST /core/term/queryStandardTerm。

**Tech Stack:** Python, dataclasses, httpx, pydantic-settings

**参考设计:** `docs/plans/2026-03-09-term-meta-design.md`

---

## Task 1: OntologyField、OntologyActionParam 增加 term_type、dataset_id

**Files:**
- Modify: `datacloud-data-service/src/datacloud_data_sdk/ontology/models.py`
- Test: `datacloud-data-service/tests/datacloud_data_sdk/test_ontology_models.py`

**Step 1: 编写失败测试**

```python
def test_ontology_field_has_term_type_and_dataset_id():
    from datacloud_data_sdk.ontology.models import OntologyField
    f = OntologyField(
        field_code="x",
        field_name="X",
        field_type="STRING",
        term_set="user.code",
        term_type="enum",
        dataset_id=12,
    )
    assert f.term_type == "enum"
    assert f.dataset_id == 12
```

**Step 2: 运行测试确认失败**

Run: `cd datacloud-data-service && PYTHONPATH=src pytest tests/datacloud_data_sdk/test_ontology_models.py::test_ontology_field_has_term_type_and_dataset_id -v`
Expected: FAIL (OntologyField 无 term_type/dataset_id)

**Step 3: 实现**

在 OntologyField 中增加 `term_type: str | None = None`、`dataset_id: int | None = None`。
在 OntologyActionParam 中增加同上。

**Step 4: 运行测试确认通过**

---

## Task 2: Loader 解析 termMeta 并填充 term_set、term_type、dataset_id

**Files:**
- Modify: `datacloud-data-service/src/datacloud_data_sdk/ontology/loader.py`
- Test: `datacloud-data-service/tests/datacloud_data_sdk/test_ontology_loader.py`（若无则新建）

**Step 1: 添加 _parse_term_meta 辅助函数**

```python
def _parse_term_meta(raw: dict) -> tuple[str | None, str | None, int | None]:
    """从 termMeta 或 term_set 解析，返回 (term_set, term_type, dataset_id)。"""
    tm = raw.get("termMeta") or raw.get("term_meta")
    if tm and isinstance(tm, dict):
        tc = tm.get("termTypeCode") or tm.get("term_type_code")
        tf = tm.get("termField") or tm.get("term_field")
        tmt = tm.get("termMasterType") or tm.get("term_master_type")
        ds = tm.get("datasetId") or tm.get("dataset_id")
        term_set = f"{tc}.{tf}" if tc and tf else None
        term_type = "enum" if tmt == "dict" else ("lookup" if tmt == "list" else None)
        dataset_id = int(ds) if ds is not None else None
        return (term_set, term_type, dataset_id)
    term_set = raw.get("term_set")
    return (term_set, None, None)
```

**Step 2: 修改 _parse_fields**

对每个 f，调用 `_parse_term_meta(f)`，得到 ts, tt, did。term_set 优先用 ts，若无则用 f.get("term_set")。传入 term_type=tt, dataset_id=did。

**Step 3: 修改 _parse_actions 的 params**

对每个 p，同上解析，传入 OntologyActionParam。

**Step 4: 编写测试**

加载含 termMeta 的 JSON，断言解析后 term_set、term_type、dataset_id 正确。

**Step 5: 运行测试**

---

## Task 3: ObjectViewField、ObjectViewFunctionParam 增加 term_type、dataset_id

**Files:**
- Modify: `datacloud-data-service/src/datacloud_data_sdk/plan/models.py`
- Test: `datacloud-data-service/tests/datacloud_data_sdk/test_plan_models.py`（若无则 test_object_view_builder）

**Step 1:** 在 ObjectViewField、ObjectViewFunctionParam 中增加 `term_type: str | None = None`、`dataset_id: int | None = None`。

**Step 2:** 运行相关测试确保无回归。

---

## Task 4: ObjectViewBuilder 传入 term_type、dataset_id

**Files:**
- Modify: `datacloud-data-service/src/datacloud_data_sdk/plan/object_view_builder.py`

**Step 1:** 构建 ObjectViewField 时传入 `term_type=f.term_type`、`dataset_id=f.dataset_id`。
构建 ObjectViewFunctionParam 时传入 `term_type=p.term_type`、`dataset_id=p.dataset_id`。

**Step 2:** 运行 `pytest tests/datacloud_data_sdk/test_object_view_builder.py -v`。

---

## Task 5: _serialize_param 优先使用 term_type

**Files:**
- Modify: `datacloud-data-service/src/datacloud_data_sdk/plan/query_plan_generator.py`

**Step 1:** 在 _serialize_param 中，若 p 有 term_type：
- term_type=="enum"：调用 term_loader.get_available_values 获取 labels，注入 termType、termLabels
- term_type=="lookup"：注入 termType、termHint
若无 term_type，保持现有逻辑（根据 term_loader 返回值推断）。

**Step 2:** 运行 `pytest tests/datacloud_data_sdk/test_query_plan_generator.py -v`。

---

## Task 6: 配置 znt_server 与 .env.example

**Files:**
- Modify: `datacloud-data-service/src/datacloud_data_service/config.py`
- Modify: `datacloud-data-service/.env.example`

**Step 1:** 在 Settings 中增加 `znt_server: str = ""`（环境变量 DC_ZNT_SERVER）。

**Step 2:** 在 .env.example 中增加 `DC_ZNT_SERVER=https://your-term-server`。

---

## Task 7: TermLoader 扩展 API 模式

**Files:**
- Modify: `datacloud-data-service/src/datacloud_data_sdk/ontology/term_loader.py`
- Test: `datacloud-data-service/tests/datacloud_data_sdk/test_term_loader.py`

**Step 1: 扩展 TermLoader**

- 新增 `configure_api(base_url: str)` 或 `__init__(mapping=None, api_base_url=None)`
- `get_available_values(term_set, dataset_id=None, term_type_code=None, keyword="")`：若配置了 API 且 dataset_id 存在，POST 请求；否则用内存 _sets
- `resolve_code(term_set, value, dataset_id=None, term_type_code=None)`：lookup 时可用 keyword=value 搜索
- 请求体：`{"datasetIds": [str(dataset_id)], "termType": term_type_code or term_set.split(".")[0], "keyword": keyword, "queryType": "fullTextRecall", "topK": 100}`
- 响应解析：termInfoList → TermEntry(code=termCode, label=termName, aliases=split(synonyms))

**Step 2: 调用方传入 dataset_id、term_type_code**

query_plan_generator 的 _serialize_param 调用 get_available_values 时，若 p 有 dataset_id，传入。term_type_code 可从 term_set 取点前部分。

**Step 3:** TermResolver.resolve_params 调用 resolve_code 时，若 param 有 dataset_id，传入；lookup 时 keyword=value。

**Step 4:** 运行测试。

---

## Task 8（可选）: 字段名兼容 properties / property_code

**Files:**
- Modify: `datacloud-data-service/src/datacloud_data_sdk/ontology/loader.py`

**Step 1:** 在 load_from_content 中，`fields = obj.get("fields", obj.get("properties", []))`。

**Step 2:** 在 _parse_fields 中，`field_code = f.get("field_code", f.get("property_code", ""))`，其余 field_name、field_type 等做类似兼容。

---

## 验收检查清单

1. 本体 JSON 含 termMeta 时，解析后 term_set、term_type、dataset_id 正确
2. 序列化给模型时，term_type 正确为 enum/lookup
3. DC_ZNT_SERVER 配置后，可调用术语 API 获取 termLabels
4. term_type=lookup 且 resolve_code 时，可通过 keyword 搜索
5. 无 termMeta 仅有 term_set 时，行为与现有一致

---

**Plan complete and saved to `docs/plans/2026-03-09-term-meta-implementation.md`.**

执行方式建议：
1. **Subagent-Driven（本会话）**：按任务分派子 agent，逐任务实现并审查
2. **Parallel Session（新会话）**：在新会话中用 executing-plans 按检查点批量执行
