# AGENTS

亦庄产业大脑 — Agent 技术驱动的产业数据分析 Demo。

## Overview

本项目是纯数据仿真环境（mock_env），为核心 SDK 包提供：
- 数据库 Schema（3 张 DWS 宽表）
- 结构化数据（CSV，~15,000 企业）
- 知识库导入包（术语库 + 本体定义）
- 测试套件（DDL → 数据加载 → 知识入库 → NL 查询）

**Agent 前后端**：`backend/`（`langgraph dev`）、`frontend/`（Deep Agents UI）；数据与知识管线仍依赖 `mock_env/` 与 `packages/datacloud-knowledge`。

## Structure

```
e_commerce_demo/
├── backend/                      # LangGraph Agent + datacloud_data_service 内嵌
├── frontend/                     # Deep Agents UI（Next.js）
└── mock_env/                     # 数据仿真环境
    ├── .env.example              # DB 连接配置模板
    ├── db/ddl/tables/            # DDL 建表语句（3 文件）
    ├── resource/
    │   ├── data/                 # CSV 数据文件（3 张表）
    │   ├── knowledge/import_package/  # 知识库导入包
    │   └── files/                # 非结构化文档（按场景分类）
    ├── docs/亦庄术语库导入文件/   # 源 Excel 术语文件
    ├── data_tools/               # ETL 脚本
    └── tests/                    # 测试套件（type1-type5）
```

## Where to Look

| 任务 | 位置 |
|------|------|
| LangGraph Agent / `langgraph dev` | `backend/` — `langgraph.json`、`agent.py` |
| 对话 UI（yarn dev） | `frontend/` |
| 理解数据模型 | `mock_env/db/ddl/tables/*.sql` — 3 张宽表定义 |
| 知识图谱结构 | `mock_env/resource/knowledge/import_package/ontology/` |
| 术语定义 | `mock_env/resource/knowledge/import_package/terms/` |
| 测试入口 | `mock_env/tests/` — 按 type1-type5 分类 |
| ETL 工具 | `mock_env/data_tools/convert_yizhuang_terms.py` |
| 场景文档 | `mock_env/resource/files/{经济活力类,偷税漏税类,...}/` |

## Data Model

### 三张 DWS 宽表

| 表名 | 主键 | 用途 |
|------|------|------|
| `dws_enterprise_wide` | enterprise_id + data_year | 企业级指标（营收/税额/风险/开票/产业链） |
| `dws_grid_wide` | grid_id + data_year | 网格级聚合（企业数/资产/IoT 活力指数） |
| `dws_industry_wide` | chain_id + data_year | 产业链级聚合（龙头企业/关系强度） |

### 表间关系

```
dws_enterprise_wide
    ├── MANY_TO_ONE → dws_grid_wide (grid_id + data_year)
    └── MANY_TO_ONE → dws_industry_wide (chain_id + data_year)

dws_industry_wide
    └── MANY_TO_ONE → dws_industry_wide (parent_chain_id, 层级自关联)
```

## Knowledge Model

### import_package 结构

```
import_package/
├── manifest.json           # 导入清单
├── meta/                   # 领域/知识库定义
├── term_types/custom.jsonl # 44 种自定义术语类型
├── terms/
│   ├── dict_terms.jsonl    # 75 字典术语（指标/维度/状态）
│   ├── list_terms.jsonl    # 16,032 列表术语（企业名/网格名/行业名）
│   └── ontology_terms.jsonl # 4 本体术语（3 对象 + 1 视图）
├── ontology/
│   ├── objects/            # DWS 表本体定义
│   └── views/              # 场景视图（定义表间关系）
├── relations/              # 术语关系（当前为空）
└── knowledge/              # 知识事实（当前为空）
```

### 领域归属

所有术语挂载到 `DOMAIN_002`（产业管理）/ `LIB_002`（产业大脑）。

### 术语结构（JSONL）

```json
{
  "op": "add",
  "term_code": "...",
  "term_name": "...",
  "term_type_code": "...",
  "domain_code": "DOMAIN_002",
  "library_code": "LIB_002",
  "parent_term_code": "TERM_TYPE_*"
}
```

## Test Categories

| 类型 | 标记 | 用途 | DB 依赖 |
|------|------|------|---------|
| type1 | `@pytest.mark.type1_schema` | DDL 验证 | 否 |
| type2 | `@pytest.mark.type2_data` | CSV→DB 加载 | 否（静态） |
| type4 | `@pytest.mark.type4_knowledge` | 知识入库 | 是 |
| type5 | `@pytest.mark.type5_nl_knowledge` | NL 查询 | 是 |

### 初始化顺序

```
type1_db_schema → type2_data_load → type4_knowledge_ingest → type5_nl_knowledge_query
```

**顺序必须正确** — 后续测试依赖前序测试的数据。

### 集成测试控制

```bash
# 静态测试（默认）
pytest tests/type1_db_schema tests/type2_data_load tests/type4_knowledge_ingest -q

# 集成测试（需 DB）
export DATACLOUD_ENABLE_INTEGRATION_TESTS=1
export DB_HOST=... DB_PORT=... DB_USER=... DB_PASSWORD=... DB_NAME=...
pytest tests -v
```

### Fixture 约定

- `mock_env_root` — mock_env 目录路径（session）
- `integration_enabled` — 检查 `DATACLOUD_ENABLE_INTEGRATION_TESTS` 环境变量
- `db_ready` — 验证 DB 前置条件（不负责初始化，条件不满足则 skip）
- `knowledge_service` — `SQLKnowledgeGraphQuery` 实例

## Commands

```bash
# 进入 mock_env 目录
cd examples/e_commerce_demo/mock_env

# 静态测试
pytest tests/type1_db_schema tests/type2_data_load tests/type4_knowledge_ingest -q

# 集成测试（需配置 DB 环境变量）
DATACLOUD_ENABLE_INTEGRATION_TESTS=1 pytest tests -v

# 运行 NL 查询测试
pytest tests/type5_nl_knowledge_query -v

# 转换 Excel 术语文件
cd data_tools && python convert_yizhuang_terms.py
```

## Conventions

### 命名规范

| 位置 | 风格 | 示例 |
|------|------|------|
| DB 列名 | snake_case | `enterprise_id`, `data_year` |
| Ontology field_code | camelCase | `enterpriseId`, `dataYear` |
| Ontology field_name | 中文 | "企业ID", "数据年份" |
| Term code | snake_case 或标识符 | `enterprise`, `VACANT`, `asc` |

### JSONL 文件约定

- 每行一个 JSON 对象
- `op` 字段固定为 `"add"`
- 术语类型前缀：`TERM_TYPE_*`

### 测试分层

- **unit** — 文件系统检查，无外部依赖
- **api-unit** — TestClient API 调用，无 DB
- **integration** — 完整流程，需真实数据库

## Notes

- **项目名有误导性**：`e_commerce_demo` 实际是工业园区经济监测平台，非电商业务
- **入口**：`backend/` + `frontend/` 为可交互 Agent；`mock_env` 仍为数据/知识仿真，NL 查询等需配合 `packages/datacloud-knowledge`
- **db_ready 不初始化**：fixture 只验证前置条件，DB 初始化需手动执行 DDL
- **知识入库前置**：type5 测试前必须完成 type4 知识导入
