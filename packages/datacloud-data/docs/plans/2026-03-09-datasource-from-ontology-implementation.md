# 数据源从本体配置 - 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 数据源配置不再依赖 YAML，改为从本体对象上的 `source_config` 解析；解析时按 alias 去重；保留 `create_app(datasource_configs=...)` 用于测试覆盖。

**Architecture:** 方案 A（对象内嵌 source_config）。OntologyLoader 在 `load_from_content()` 完成后，遍历 `source_type=DB` 且含 `source_config` 的对象，提取并去重，产出 `dict[str, DataSourceConfig]`，写入 `LoaderConfig.datasource_configs`。routes 中若未传入 `datasource_configs`，则依赖 loader 内部产出；`datasources_yaml_path` 废弃。

**Tech Stack:** Python 3.12, pydantic-settings, datacloud_data_sdk (OntologyLoader, DataSourceConfig, config_loader)

**Design Doc:** `docs/plans/2026-03-09-datasource-from-ontology-design.md`

---

## Task 1: OntologyClass 新增 source_config 字段

**Files:**
- Modify: `src/datacloud_data_sdk/ontology/models.py`
- Test: `tests/datacloud_data_sdk/test_ontology_loader.py`

**Step 1: Write the failing test**

在 `test_ontology_loader.py` 新增：

```python
def test_ontology_class_parses_source_config() -> None:
    """对象含 source_config 时，OntologyClass 能解析并存储。"""
    loader = OntologyLoader()
    content = {
        "objects": [
            {
                "object_code": "test_obj",
                "object_name": "测试对象",
                "source_type": "DB",
                "table_name": "test_table",
                "source_config": {
                    "alias": "ds_test",
                    "db_type": "MYSQL",
                    "jdbc_url": "jdbc:mysql://localhost:3306/test",
                },
                "fields": [],
                "actions": [],
            }
        ],
        "relations": [],
    }
    loader.load_from_content(content)
    cls = loader.get_ontology_class("test_obj")
    assert cls.source_config is not None
    assert cls.source_config.get("alias") == "ds_test"
    assert cls.datasource_alias == "ds_test"  # 从 source_config.alias 推导
```

**Step 2: Run test to verify it fails**

Run: `cd datacloud-data-service && pytest tests/datacloud_data_sdk/test_ontology_loader.py::test_ontology_class_parses_source_config -v`
Expected: FAIL (OntologyClass 无 source_config，或 loader 未解析)

**Step 3: Implement**

- 在 `OntologyClass` 新增 `source_config: dict | None = None`
- 在 `loader.load_from_content()` 解析 objects 时，传入 `source_config=obj.get("source_config")`
- 若 `source_config` 存在且含 `alias`，则 `datasource_alias = source_config.get("alias")`，否则用 `obj.get("datasource_alias")`

**Step 4: Run test**

Run: `pytest tests/datacloud_data_sdk/test_ontology_loader.py::test_ontology_class_parses_source_config -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/datacloud_data_sdk/ontology/models.py src/datacloud_data_sdk/ontology/loader.py tests/datacloud_data_sdk/test_ontology_loader.py
git commit -m "feat(ontology): add source_config to OntologyClass and parse from objects"
```

---

## Task 2: Loader 新增 _extract_datasource_configs_from_objects

**Files:**
- Modify: `src/datacloud_data_sdk/ontology/loader.py`
- Modify: `src/datacloud_data_sdk/sql_executor/config_loader.py`（确保 `_dict_to_config`、`_substitute_dict` 可被 ontology 模块调用）
- Test: `tests/datacloud_data_sdk/test_ontology_loader.py`

**Step 1: Write the failing test**

```python
def test_extract_datasource_configs_from_objects() -> None:
    """从对象 source_config 提取 DataSourceConfig，按 alias 去重。"""
    loader = OntologyLoader()
    content = {
        "objects": [
            {
                "object_code": "obj1",
                "object_name": "对象1",
                "source_type": "DB",
                "table_name": "t1",
                "source_config": {
                    "alias": "ds_crm",
                    "db_type": "MYSQL",
                    "jdbc_url": "jdbc:mysql://localhost:3306/crm",
                    "user": "root",
                    "password": "secret",
                    "pool_min": 1,
                    "pool_max": 5,
                },
                "fields": [],
                "actions": [],
            },
            {
                "object_code": "obj2",
                "object_name": "对象2",
                "source_type": "DB",
                "table_name": "t2",
                "source_config": {
                    "alias": "ds_crm",
                    "db_type": "MYSQL",
                    "jdbc_url": "jdbc:mysql://localhost:3306/crm",
                    "user": "root",
                    "password": "secret",
                },
                "fields": [],
                "actions": [],
            },
        ],
        "relations": [],
    }
    loader.load_from_content(content)
    configs = loader._extract_datasource_configs_from_objects()
    assert len(configs) == 1
    assert "ds_crm" in configs
    assert configs["ds_crm"].db_type == "MYSQL"
    assert configs["ds_crm"].jdbc_url == "jdbc:mysql://localhost:3306/crm"
```

**Step 2: Run test**

Run: `pytest tests/datacloud_data_sdk/test_ontology_loader.py::test_extract_datasource_configs_from_objects -v`
Expected: FAIL

**Step 3: Implement**

在 `loader.py` 新增：

```python
def _extract_datasource_configs_from_objects(self) -> dict[str, Any]:
    """从 source_type=DB 且含 source_config 的对象提取 DataSourceConfig，按 alias 去重。"""
    from datacloud_data_sdk.sql_executor.config_loader import (
        _dict_to_config,
        _substitute_dict,
    )

    configs: dict[str, Any] = {}
    for cls in self._classes.values():
        if cls.source_type != "DB" or not cls.source_config:
            continue
        sc = cls.source_config
        alias = sc.get("alias") or cls.datasource_alias
        if not alias or alias in configs:
            continue
        substituted = _substitute_dict(dict(sc))
        configs[alias] = _dict_to_config(alias, substituted)
    return configs
```

**Step 4: Run test**

Expected: PASS

**Step 5: Commit**

```bash
git add src/datacloud_data_sdk/ontology/loader.py tests/datacloud_data_sdk/test_ontology_loader.py
git commit -m "feat(ontology): add _extract_datasource_configs_from_objects"
```

---

## Task 3: load_from_content 完成后自动注入 datasource_configs

**Files:**
- Modify: `src/datacloud_data_sdk/ontology/loader.py`
- Test: `tests/datacloud_data_sdk/test_ontology_loader.py`

**Step 1: Write the failing test**

```python
def test_load_from_content_auto_injects_datasource_configs() -> None:
    """load_from_content 完成后，datasource_configs 自动注入。"""
    loader = OntologyLoader()
    content = {
        "objects": [
            {
                "object_code": "obj1",
                "object_name": "对象1",
                "source_type": "DB",
                "table_name": "t1",
                "source_config": {
                    "alias": "ds_test",
                    "db_type": "SQLITE",
                    "jdbc_url": "jdbc:sqlite::memory:",
                },
                "fields": [],
                "actions": [],
            }
        ],
        "relations": [],
    }
    loader.load_from_content(content)
    assert loader._config.datasource_configs
    assert "ds_test" in loader._config.datasource_configs
```

**Step 2: Run test**

Expected: FAIL

**Step 3: Implement**

在 `load_from_content()` 末尾（for rel in relations 之后）添加：

```python
extracted = self._extract_datasource_configs_from_objects()
if extracted:
    self._config.datasource_configs = {
        **self._config.datasource_configs,
        **extracted,
    }
```

注意：若 `configure(datasource_configs=...)` 已传入，应尊重传入值。当前逻辑是 merge，即本体提取的会与已有合并。设计上：`create_app(datasource_configs=...)` 传入时，routes 不会调用 `_build_datasource_configs`，直接传 configs 给 loader.configure，此时 loader 的 datasource_configs 会被覆盖。因此 load 时自动注入后，若后续 configure 传入 datasource_configs，会覆盖。需确认：load 在 configure 之前执行，所以 load 时注入的 configs 会在 configure 时被覆盖。OK，逻辑正确。

**Step 4: Run test**

Expected: PASS

**Step 5: Commit**

```bash
git add src/datacloud_data_sdk/ontology/loader.py tests/datacloud_data_sdk/test_ontology_loader.py
git commit -m "feat(ontology): auto-inject datasource_configs after load_from_content"
```

---

## Task 4: routes 移除 YAML 逻辑，改为依赖 loader 内部产出

**Files:**
- Modify: `src/datacloud_data_service/api/routes.py`
- Modify: `src/datacloud_data_service/config.py`
- Test: `tests/datacloud_data_service/test_health.py`

**Step 1: 修改 routes**

- 删除或简化 `_build_datasource_configs()`：不再读取 `datasources_yaml_path` 和 `settings.datasources`
- lifespan 中：`configs = datasource_configs if datasource_configs is not None else loader._config.datasource_configs`
- 若 configs 非空，则 `loader.configure(datasource_configs=configs)`（测试传入时覆盖本体提取的）

**Step 2: 修改 config**

- 移除 `datasources_yaml_path`、`datasources`，或标记为 deprecated（保留字段但不再使用）

**Step 3: 运行现有测试**

Run: `pytest tests/datacloud_data_service/ -v`
Expected: test_health_check 可能失败（无 datasource_configs 传入且本体无 source_config）

**Step 4: 调整 test_health**

- `test_health_check()`：无 datasource 时返回 `{"status":"ok"}`，应仍通过
- `test_health_check_with_datasources()`：需通过本体内容或 `create_app(datasource_configs=...)` 注入。保留 `create_app(datasource_configs=...)`，该测试继续用传入方式

**Step 5: Commit**

```bash
git add src/datacloud_data_service/api/routes.py src/datacloud_data_service/config.py
git commit -m "refactor(routes): remove YAML datasource loading, use loader-extracted configs"
```

---

## Task 5: 为 objects_registry.json 中 DB 对象补充 source_config

**Files:**
- Modify: `resources/ontology/crm_demo/objects_registry.json`

**Step 1: 识别需补充的对象**

grep `"source_type": "DB"` 或 `"datasource_alias"` 且非 null 的对象。

**Step 2: 为每个 DB 对象添加 source_config**

示例（ds_crm 对应多个对象，每个都写一份，解析时会去重）：

```json
{
  "object_code": "sales_business_opportunity",
  "source_type": "DB",
  "datasource_alias": "ds_crm",
  "table_name": "sales_business_opportunity",
  "source_config": {
    "alias": "ds_crm",
    "db_type": "SQLITE",
    "jdbc_url": "jdbc:sqlite::memory:",
    "user": "",
    "password": "",
    "pool_min": 1,
    "pool_max": 5
  },
  ...
}
```

本地开发用 SQLite 内存；生产可改为 MySQL 或通过 `${DB_PASSWORD}` 等环境变量。

**Step 3: 运行 e2e 或集成测试**

Run: `pytest tests/e2e/ tests/datacloud_data_service/ -v`
Expected: 通过或根据实际情况调整

**Step 4: Commit**

```bash
git add resources/ontology/crm_demo/objects_registry.json
git commit -m "feat(ontology): add source_config to DB objects in crm_demo"
```

---

## Task 6: 更新 .env.example 和 README

**Files:**
- Modify: `datacloud-data-service/.env.example`
- Modify: `datacloud-data-service/README.md`

**Step 1: 移除 DC_DATASOURCES_YAML_PATH**

从 .env.example 删除或注释该行及说明。

**Step 2: 更新 README 配置说明**

说明数据源来自本体对象 `source_config`，不再需要单独配置 YAML。

**Step 3: Commit**

```bash
git add .env.example README.md
git commit -m "docs: update config docs for datasource-from-ontology"
```

---

## Task 7: 调整其余测试以通过本体或 datasource_configs 注入

**Files:**
- Modify: `tests/datacloud_data_service/test_rest_query.py`
- Modify: `tests/datacloud_data_service/test_skills_api.py`
- Modify: `tests/datacloud_data_sdk/integration/test_query_pipeline_integration.py`
- Modify: `tests/e2e/test_crm_scenarios.py`

**Step 1: 检查各测试**

若测试通过 `create_app(datasource_configs=...)` 传入 configs，保持不变。若依赖 YAML 或默认 configs，改为传入或使用含 source_config 的本体 fixture。

**Step 2: 运行全量测试**

Run: `pytest tests/ -v`
Expected: 全部通过

**Step 3: Commit**

```bash
git add tests/
git commit -m "test: align tests with datasource-from-ontology"
```

---

## Execution Handoff

Plan complete and saved to `docs/plans/2026-03-09-datasource-from-ontology-implementation.md`.

**Two execution options:**

1. **Subagent-Driven (this session)** - Dispatch fresh subagent per task, review between tasks, fast iteration
2. **Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?**
