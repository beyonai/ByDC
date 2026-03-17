# 数据源从本体配置设计

**日期**: 2026-03-09  
**目标**: 数据源配置不再依赖 YAML，改为从本体（对象）上的配置解析  
**选定方案**: 方案 A（对象内嵌 source_config），解析时按 alias 去重；后续使用中可再抽取公共数据源

---

## 1. 涉及修改的位置清单

### 1.1 配置与入口层

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `datacloud_data_service/config.py` | **删除/废弃** | 移除 `datasources_yaml_path`、`datasources`；或保留作兼容/覆盖 |
| `datacloud_data_service/api/routes.py` | **重构** | `_build_datasource_configs()` 改为从 loader 解析后的对象提取；或删除该函数，由 loader 内部产出 |
| `.env.example` | **更新** | 移除 `DC_DATASOURCES_YAML_PATH` 相关说明 |
| `config/datasources.yaml.example` | **删除或废弃** | 不再作为主配置方式 |

### 1.2 本体加载与解析层

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `datacloud_data/ontology/loader.py` | **核心修改** | 1) `load_from_content()` 解析对象上的 `source_config`；2) 新增 `_extract_datasource_configs_from_objects()` 遍历 `source_type=DB` 且含 `source_config` 的对象，产出 `dict[str, DataSourceConfig]`，按 `alias` 去重；3) load 完成后自动调用并写入 `LoaderConfig.datasource_configs` |
| `datacloud_data/ontology/models.py` | **扩展** | `OntologyClass` 新增 `source_config: dict \| None` 字段 |

### 1.3 配置加载工具层

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `datacloud_data/sql_executor/config_loader.py` | **扩展/复用** | 1) 保留 `_dict_to_config()`、`_substitute_dict()` 供本体解析复用；2) `load_datasources_from_yaml()` 可保留作兼容或标记废弃 |

### 1.4 执行层（基本不变）

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `datacloud_data/object.py` | **无/微调** | 继续使用 `config.datasource_configs`，来源改为 loader 内部产出 |
| `datacloud_data/view.py` | **无** | 同上 |
| `datacloud_data/sql_executor/sql_executor.py` | **无** | 仍通过 `DataSourceManager(configs)` 执行 |
| `datacloud_data/sql_executor/data_source_manager.py` | **无** | 接口不变 |
| `datacloud_data/sql_executor/models.py` | **无** | `DataSourceConfig` 结构不变 |

### 1.5 测试层

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `tests/datacloud_data_service/test_health.py` | **调整** | 若不再支持 `datasource_configs` 入参，需改为通过本体 mock 注入 |
| `tests/datacloud_data_service/test_rest_query.py` | **调整** | 同上 |
| `tests/datacloud_data_service/test_skills_api.py` | **调整** | 同上 |
| `tests/datacloud_data/test_config_loader.py` | **保留/废弃** | 若 YAML 加载废弃，测试可保留作回归或删除 |
| `tests/datacloud_data/integration/test_query_pipeline_integration.py` | **调整** | 改为通过本体内容注入数据源 |
| `tests/e2e/test_crm_scenarios.py` | **调整** | 同上 |

### 1.6 本体资源文件

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `resources/ontology/crm_demo/objects_registry.json` | **扩展** | 按选定方案补充 `source_config` 或顶层 `datasources` |

### 1.7 文档

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `README.md` | **更新** | 配置说明改为「数据源来自本体」 |
| `docs/本地对象标准格式规范*.md` | **更新** | 补充 `source_config` / `datasources` 规范 |

---

## 2. 数据流变化（当前 vs 目标）

### 当前

```
.env / settings
  → DC_DATASOURCES_YAML_PATH
  → routes._build_datasource_configs()
  → load_datasources_from_yaml() 或 settings.datasources
  → loader.configure(datasource_configs=...)
  → LoaderConfig.datasource_configs
  → Object/View → DataSourceManager
```

### 目标（方案 A，已选定）

```
ontology JSON
  → loader.load_from_path()
  → load_from_content() 解析 objects[].source_config
  → _extract_datasource_configs() 遍历 source_type=DB 的对象，提取 source_config，按 alias 去重（同 alias 只保留一份）
  → loader._config.datasource_configs（自动注入）
  → Object/View → DataSourceManager
```

**后续演进**：使用中若发现多对象共用同一数据源，可再抽取为顶层 `datasources` 或独立配置文件，对象改为 `datasource_alias` 引用。

---

## 3. 方案 A vs B 具体样例

### 3.1 方案 A：对象内嵌 source_config

每个 DB 类型对象在自身内嵌完整连接配置。多个对象共用同一数据源时，连接信息会重复。

```json
{
  "objects": [
    {
      "object_code": "sales_business_opportunity",
      "object_name": "商机对象",
      "source_type": "DB",
      "table_name": "sales_business_opportunity",
      "source_config": {
        "alias": "ds_crm",
        "db_type": "MYSQL",
        "jdbc_url": "jdbc:mysql://localhost:3306/crm",
        "user": "root",
        "password": "${DB_PASSWORD}",
        "pool_min": 1,
        "pool_max": 5
      },
      "fields": [...]
    },
    {
      "object_code": "sales_customer",
      "object_name": "客户对象",
      "source_type": "DB",
      "table_name": "sales_customer",
      "source_config": {
        "alias": "ds_crm",
        "db_type": "MYSQL",
        "jdbc_url": "jdbc:mysql://localhost:3306/crm",
        "user": "root",
        "password": "${DB_PASSWORD}",
        "pool_min": 1,
        "pool_max": 5
      },
      "fields": [...]
    }
  ]
}
```

**特点**：对象自包含，迁移/导出单对象即可；同一库多对象时连接配置重复，解析时需按 `alias` 去重。

---

### 3.2 方案 B：本体顶层 datasources

连接配置集中在文件顶层，对象通过 `datasource_alias` 引用。

```json
{
  "datasources": {
    "ds_crm": {
      "alias": "ds_crm",
      "db_type": "MYSQL",
      "jdbc_url": "jdbc:mysql://localhost:3306/crm",
      "user": "root",
      "password": "${DB_PASSWORD}",
      "pool_min": 1,
      "pool_max": 5
    },
    "ds_attendance": {
      "alias": "ds_attendance",
      "db_type": "MYSQL",
      "jdbc_url": "jdbc:mysql://localhost:3307/attendance",
      "user": "att_user",
      "password": "${ATT_DB_PASSWORD}",
      "pool_min": 1,
      "pool_max": 5
    }
  },
  "objects": [
    {
      "object_code": "sales_business_opportunity",
      "object_name": "商机对象",
      "source_type": "DB",
      "datasource_alias": "ds_crm",
      "table_name": "sales_business_opportunity",
      "fields": [...]
    },
    {
      "object_code": "sales_customer",
      "object_name": "客户对象",
      "source_type": "DB",
      "datasource_alias": "ds_crm",
      "table_name": "sales_customer",
      "fields": [...]
    },
    {
      "object_code": "sales_emp_attendance",
      "object_name": "考勤对象",
      "source_type": "DB",
      "datasource_alias": "ds_attendance",
      "table_name": "emp_attendance",
      "fields": [...]
    }
  ]
}
```

**特点**：连接配置集中、无重复；对象定义更简洁；与当前 `datasource_alias` + `table_name` 结构一致，改动最小。

---

### 3.3 方案对比

| 维度 | 方案 A（对象内嵌） | 方案 B（顶层 datasources） |
|------|-------------------|---------------------------|
| 配置重复 | 多对象同库时重复 | 无重复 |
| 对象自包含 | ✅ 单对象可独立迁移 | ❌ 依赖顶层 datasources |
| 与现有格式兼容 | 需新增 source_config 解析 | 仅新增顶层节点，对象结构不变 |
| 解析逻辑 | 遍历对象提取、按 alias 去重 | 直接读 content["datasources"] |
| 推荐 | 适合对象级分发场景 | **推荐**：结构清晰，改动小 |

---

## 4. 已确认项

| 项 | 决策 |
|----|------|
| 方案 | 方案 A（对象内嵌 source_config） |
| 去重策略 | 解析时按 `source_config.alias` 去重，同 alias 只保留第一份 |
| 兼容策略 | 保留 `create_app(datasource_configs=...)` 用于测试覆盖；`datasources_yaml_path` 废弃 |
| KB 数据源 | 暂不迁入本体，保持现状 |

---

## 5. 修改点汇总

| 层级 | 文件数 | 主要动作 |
|------|--------|----------|
| 配置/入口 | 4 | 移除 YAML 路径配置，重构 routes 中 datasource 构建逻辑 |
| 本体加载 | 2 | loader 解析 source_config/datasources，自动产出 datasource_configs |
| 配置工具 | 1 | 复用 _dict_to_config 等，YAML 加载可选废弃 |
| 测试 | 6 | 改为通过本体 mock 注入数据源 |
| 本体资源 | 1 | 补充数据源定义 |
| 文档 | 2+ | 更新配置说明与格式规范 |

**合计**：约 16 个文件/位置涉及修改。

---

## 6. 方案 A 实现要点

### 6.1 source_config 结构

与 `DataSourceConfig` 对齐，支持 `${ENV_VAR}` 环境变量替换：

```json
{
  "alias": "ds_crm",
  "db_type": "MYSQL",
  "jdbc_url": "jdbc:mysql://localhost:3306/crm",
  "user": "root",
  "password": "${DB_PASSWORD}",
  "pool_min": 1,
  "pool_max": 5
}
```

### 6.2 解析与去重

- 仅处理 `source_type=DB` 且 `source_config` 非空的对象
- 用 `config_loader._dict_to_config(alias, source_config)` 转为 `DataSourceConfig`
- 按 `alias` 去重：`configs[alias] = cfg`，已存在则跳过（或覆盖，同 alias 配置应一致）
- 对 `source_config` 做 `_substitute_dict()` 环境变量替换

### 6.3 兼容与覆盖

- `create_app(datasource_configs=...)` 保留：若传入则优先使用，不从本体提取
- `datasources_yaml_path` 废弃：不再读取，可从 config 移除
