# datacloud-data

数据服务（Data Service）是 DataCloud 2.0 的核心服务之一，负责执行数据查询、返回数据结果，并提供行列权限控制。

**datacloud-data** 同时包含 SDK（面向开发者的Python包）和 Service（面向部署的 FastAPI 服务），支持自然语言转 SQL、DSL 查询、异构数据源适配和权限控制。

## 环境要求

- **Python**: >= 3.12（**注意**：Python 3.11 不支持，请使用 3.12 及以上版本）
- **操作系统**: macOS / Linux
- **包管理器**: uv（推荐）或 pip

## 快速开始（一键安装全部依赖并运行）

### 步骤 1：检查 Python 版本

```bash
python --version  # 确保是 3.12 或更高版本
```

### 步骤 2：安装 uv（如未安装）

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# 或使用 pip
pip install uv
```

### 步骤 3：进入项目目录并创建虚拟环境

```bash
cd packages/datacloud-data
uv venv .venv --python 3.12
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows
```

### 步骤 4：安装全部依赖

```bash
# 方式一：使用 uv（推荐，更快）
uv pip install -e ".[all]"

# 方式二：使用 pip
pip install -e ".[all]"
```

### 步骤 5：配置环境变量

```bash
cp .env.example .env
# 根据需要编辑 .env 文件
```

### 步骤 6：启动服务

```bash
uvicorn datacloud_data_service.api.routes:create_app --factory --host 0.0.0.0 --port 8080
```

### 步骤 7：验证服务

```bash
# 健康检查
curl http://localhost:8080/health

# 预期返回
{"status": "ok"}
```

---

## 可选依赖组

| 组名 | 说明 | 安装命令 |
|------|------|----------|
| `langchain` | LangGraph + LangChain OpenAI（NL2SQL LLM调用） | `uv pip install -e ".[langchain]"` |
| `sql` | SQLAlchemy + MySQL/PostgreSQL/SQLite/OpenGauss 驱动 | `uv pip install -e ".[sql]"` |
| `clickhouse` | ClickHouse 连接器 | `uv pip install -e ".[clickhouse]"` |
| `service` | FastAPI + Uvicorn + MCP 支持 | `uv pip install -e ".[service]"` |
| `knowledge` | 知识库模式支持 | `uv pip install -e ".[knowledge]"` |
| `all` | **所有依赖（推荐）** | `uv pip install -e ".[all]"` |
| `dev` | 开发测试依赖（pytest/ruff/mypy） | `uv pip install -e ".[dev]"` |

---

## 环境变量配置

复制环境变量模板并按需修改：

```bash
cp .env.example .env
```

### 关键环境变量说明

#### LLM 配置（自然语言转 SQL，不配置则 NL2SQL 不可用）

| 变量名 | 必填 | 说明 | 示例 |
|--------|------|------|------|
| `DC_LLM_API_KEY` | NL2SQL时必填 | LLM API Key | `sk-xxx` |
| `DC_LLM_BASE_URL` | NL2SQL时必填 | LLM 服务地址 | `https://lab.iwhalecloud.com/gpt-proxy/v1` |
| `DC_LLM_MODEL` | 否 | LLM 模型名称 | `Qwen/Qwen3-Coder-30B-Instruct` |
| `DC_LLM_TEMPERATURE` | 否 | LLM 温度参数，默认 `0.0` | `0.0` |

#### 本体与场景配置

| 变量名 | 必填 | 说明 | 示例 |
|--------|------|------|------|
| `DC_ONTOLOGY_PATH` | 是 | 本体 JSON 文件路径 | `../../examples/e_commerce_demo/mock_env/resource/knowledge/import_package/ontology/e_commerce_scene_01_data_analysis_full.json` |
| `DC_SCENE_PATH` | 否 | 场景 JSON 文件路径 | `../../examples/e_commerce_demo/mock_env/resource/knowledge/import_package/ontology/e_commerce_scene_01_data_analysis_full.json` |

#### 术语服务配置

| 变量名 | 必填 | 说明 | 示例 |
|--------|------|------|------|
| `DC_TERM_LOADER_TYPE` | 否 | 术语加载模式：`api` 或 `kb`，默认 `api` | `kb` |
| `DC_ZNT_SERVER` | api模式时必填 | 术语服务 API 地址 | `https://byai.iwhalecloud.com/developer/knowledgeService` |

#### 知识库数据库配置（KB 模式时需要）

| 变量名 | 必填 | 说明 | 示例 |
|--------|------|------|------|
| `DB_HOST` | KB模式时必填 | 数据库地址 | `10.10.179.2` |
| `DB_PORT` | KB模式时必填 | 数据库端口 | `5432` |
| `DB_USER` | KB模式时必填 | 数据库用户名 | `gaussdb` |
| `DB_PASSWORD` | KB模式时必填 | 数据库密码 | `Admin@123` |
| `DB_NAME` | KB模式时必填 | 数据库名称 | `postgres` |
| `KNOWLEDGE_DB_TYPE` | KB模式时必填 | 知识库数据库类型 | `opengauss` |
| `KNOWLEDGE_SCHEMA` | KB模式时必填 | 知识库 Schema 名称 | `whale_datacloud` |

#### 其他配置

| 变量名 | 必填 | 说明 | 示例 |
|--------|------|------|------|
| `DC_CSV_BASE_DIR` | 否 | CSV 临时文件目录，默认 `./tmp/csv` | `./tmp/csv` |
| `DC_SQL_EXECUTION_MODE` | 否 | SQL 执行模式：`internal`（内置）或 `external`（HTTP 调外部服务），默认 `internal` | `internal` |
| `DC_MAX_PLAN_RETRIES` | 否 | 最大计划重试次数，默认 2 | `2` |
| `DC_TRACE_ENABLED` | 否 | 是否启用链路追踪，默认 `false` | `false` |

### 数据源配置

数据源配置有两种方式：

1. **本体配置（推荐）**：在本体对象的 `source_config` 中定义数据源
2. **YAML配置**：使用 `config/datasources.yaml` 文件

```bash
cp config/datasources.yaml.example config/datasources.yaml
```

---

## 启动服务

### 方式一：直接使用 uvicorn（推荐）

```bash
# 确保已激活虚拟环境
source .venv/bin/activate

# 启动服务
uvicorn datacloud_data_service.api.routes:create_app --factory --host 0.0.0.0 --port 8080
```

### 方式二：使用 uv run

```bash
uv run uvicorn datacloud_data_service.api.routes:create_app --factory --host 0.0.0.0 --port 8080
```

### 方式三：在代码中创建应用

```python
import sys
sys.path.insert(0, "src")

from datacloud_data_service.api.routes import create_app

app = create_app()
```

### 启动参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--host` | `0.0.0.0` | 监听地址 |
| `--port` | `8080` | 监听端口 |
| `--workers` | `1` | 工作进程数（生产环境建议使用 gunicorn） |

---

## SDK 使用示例

### 运行完整示例

```bash
# 确保已安装全部依赖
PYTHONPATH=src python examples/all_interfaces_example.py
```

### SDK 基本用法

```python
import sys
sys.path.insert(0, "src")

from datacloud_data_sdk import OntologyLoader, InvocationContext
from datacloud_data_sdk.plan.query_plan_generator import MockPlanGenerator
from datacloud_data_sdk.sql_executor.models import DataSourceConfig

loader = OntologyLoader()
loader.load_from_content(REGISTRY)  # 或 loader.load_from_file("objects_registry.json")
loader.configure(
    plan_generator=MockPlanGenerator(fixed_plan=MOCK_PLAN),
    datasource_configs={
        "test_db": DataSourceConfig(
            alias="test_db", db_type="SQLITE", jdbc_url="jdbc:sqlite::memory:"
        )
    },
    csv_base_dir="/tmp/datacloud_csv",
)

obj = loader.get_object("sales_bo")
with InvocationContext(tenant_id="t1", user_id="u1"):
    result = await obj.query("查商机", include_plan=True)
```

### REST API 用法

```bash
# 执行查询
curl --location --request POST 'http://localhost:8080/api/v1/query' \
--header 'Content-Type: application/json' \
--header 'X-Tenant-Id: tenant-001' \
--header 'X-User-Id: user-001' \
--header 'X-Session-Id: session-001' \
--header 'Authorization: Bearer your-token' \
--header 'X-System-Code: crm' \
--data-raw '{
    "question": "2026年北京亦庄经济技术开发区区域内单位亩产效益最低的10家企业",
    "view_id": "",
    "object_ids": []
}'

# 获取数据
curl -H "Authorization: Bearer {token}" \
  http://localhost:8080/api/v1/data/{query_id}
```

## 项目结构

```
datacloud-data/
├── src/
│   ├── datacloud_data_sdk/        # SDK 核心包
│   │   ├── agents/                # LLM Agent
│   │   ├── aggregator/             # 结果聚合
│   │   ├── csv_storage/           # CSV 大文件存储
│   │   ├── events/                # 事件总线
│   │   ├── executor/               # 查询执行器
│   │   ├── graphql/               # GraphQL 支持
│   │   ├── ontology/              # 本体加载
│   │   ├── plan/                  # 查询计划
│   │   ├── sql_executor/          # SQL 执行层
│   │   └── utils/                 # 工具函数
│   └── datacloud_data_service/    # FastAPI 服务
│       ├── api/                   # API 路由
│       └── tools/                 # MCP Tools
├── config/
│   └── datasources.yaml.example   # 数据源配置示例
├── examples/
│   └── all_interfaces_example.py  # 全接口示例
├── resources/
│   └── ontology/                  # 本体定义
├── scripts/
│   └── export_scene_json.py       # 场景导出脚本
├── .env.example                   # 环境变量示例
└── pyproject.toml                 # 项目配置
```

## 开发脚本

### 导出场景完整 JSON

```bash
python scripts/export_scene_json.py \
  --scene resources/ontology/crm_demo/scene_01_data_analysis.json \
  --registry resources/ontology/crm_demo/objects_registry.json \
  --output resources/ontology/crm_demo/scene_01_data_analysis_full.json
```

## 代码检查

```bash
cd packages/datacloud-data

# Lint
ruff check src/

# Format
ruff format src/

# Type check
mypy src/

# Test
pytest tests/
```

## 相关文档

- [数据服务详细设计](../../story/V202602/feature_datacloud2.0设计/本体服务_模块设计/数据服务详细设计.md)
- [dataCloud 2.0 概要设计](../../story/V202602/feature_datacloud2.0设计/dataCloud2.0概要设计.md)

## 许可证

Apache License 2.0
