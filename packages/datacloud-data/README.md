# datacloud-data

数据服务（Data Service）是 DataCloud 2.0 的核心服务之一，负责执行数据查询、返回数据结果，并提供行列权限控制。

**datacloud-data** 同时包含 SDK（面向开发者的Python包）和 Service（面向部署的 FastAPI 服务），支持自然语言转 SQL、DSL 查询、异构数据源适配和权限控制。

## 从 PyPI 安装

```bash
pip install datacloud-data
```

按需安装扩展依赖：

```bash
pip install "datacloud-data[sql]"
pip install "datacloud-data[service]"
pip install "datacloud-data[all]"
```

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

#### 知识库数据库配置（术语加载需要）

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

### SDK 用例所需环境变量

下面这些环境变量是上面 SDK 直调用例最常见会用到的。

最小必需配置是 LLM 相关变量，因为 `LangGraphPlanGenerator` 会真实调用 Agent 生成执行计划：

```bash
# 1. LLM / Agent 规划
export DC_LLM_API_KEY="your-api-key"
export DC_LLM_BASE_URL="https://api.openai.com/v1"
export DC_LLM_MODEL="gpt-4o"
export DC_LLM_TEMPERATURE="0.0"
export DC_MAX_PLAN_RETRIES="2"

# 2. 术语加载（知识库）
# export DB_HOST="127.0.0.1"
# export DB_PORT="5432"
# export DB_USER="postgres"
# export DB_PASSWORD="password"
# export DB_NAME="postgres"
# export KNOWLEDGE_DB_TYPE="opengauss"
# export KNOWLEDGE_SCHEMA="whale_datacloud"

# 3. 查询运行目录
export DC_CSV_BASE_DIR="./tmp"
export DC_SQL_EXECUTION_MODE="internal"
```

说明：

- 如果不配置 `DC_LLM_API_KEY`，`LangGraphPlanGenerator(...)` 这类自然语言查询能力无法正常工作
- `TermLoader.from_config({})` 现在固定使用知识库术语加载器
- 术语解析依赖知识库数据库连接配置
- 如果你在代码里像下面示例一样手动 `load_from_path(...)` / `load_scene_from_path(...)`，那么 `DC_ONTOLOGY_PATH`、`DC_SCENE_PATH` 不是必需的
- 如果你把路径也想交给环境变量管理，可以在代码里读取 `DC_ONTOLOGY_PATH`、`DC_SCENE_PATH`
- `sales_business_opportunity` 这类 DB 对象查询依赖本体内配置的数据源可连通
- `todo_items`、`po_users` 这类 API 动作调用依赖对应 HTTP 服务可访问

### SDK 基本用法

```python
import sys
sys.path.insert(0, "src")

from pathlib import Path

from datacloud_data_sdk import InvocationContext, OntologyLoader
from datacloud_data_sdk.ontology.term_loader import TermLoader
from datacloud_data_sdk.plan.query_plan_generator import LangGraphPlanGenerator

loader = OntologyLoader()
loader.load_from_path("resources/ontology/crm_demo/objects_registry.json")
loader.load_scene_from_path("resources/ontology/crm_demo/views/scene_01_data_analysis.json")

loader.configure(
    plan_generator=LangGraphPlanGenerator(
        model="gpt-4o",
        base_url="https://api.openai.com/v1",
        api_key="your-api-key",
        temperature=0.0,
        max_retries=2,
    ),
    term_loader=TermLoader.from_config({}),
    csv_base_dir=str(Path("./tmp").resolve()),
    sql_execution_mode="internal",
)

view = loader.get_view("scene_01_data_analysis")
with InvocationContext(tenant_id="t1", user_id="u1"):
    result = await view.query("查询销售额前10的产品", include_plan=True)

print(result["records"])
print(result.get("plan"))
```

补充说明：

- 这里使用的是真实 `LangGraphPlanGenerator`，底层会调用 `PlanAgent.run(...)` 生成计划，而不是 Mock
- 如果只 `load_from_path(...)` 没有 `load_scene_from_path(...)`，则 `loader.get_view(...)` 不可用
- 对象里的 `source_config` 会自动提取为数据源配置，通常不需要手工再传 `datasource_configs`

### SDK 按对象查询（真实 Agent 规划）

如果你的问题只针对一个对象，可以直接用 `loader.get_object(...).query(...)`：

```python
import sys
sys.path.insert(0, "src")

import asyncio
from pathlib import Path

from datacloud_data_sdk import InvocationContext, OntologyLoader
from datacloud_data_sdk.ontology.term_loader import TermLoader
from datacloud_data_sdk.plan.query_plan_generator import LangGraphPlanGenerator


async def main() -> None:
    loader = OntologyLoader()
    loader.load_from_path("resources/ontology/crm_demo/objects_registry.json")
    loader.configure(
        plan_generator=LangGraphPlanGenerator(
            model="gpt-4o",
            base_url="https://api.openai.com/v1",
            api_key="your-api-key",
            temperature=0.0,
            max_retries=2,
        ),
        term_loader=TermLoader.from_config({}),
        csv_base_dir=str(Path("./tmp").resolve()),
        sql_execution_mode="internal",
    )

    obj = loader.get_object("sales_business_opportunity")
    with InvocationContext(tenant_id="t1", user_id="u1"):
        result = await obj.query("查询最近30天我的商机列表", include_plan=True)

    print(result)


asyncio.run(main())
```

`sales_business_opportunity` 是 `crm_demo` 中的 DB 对象，适合验证自然语言查询是否真正走了 Agent 规划和 SQL 执行链路。

### SDK 按视图查询（真实 Agent 规划）

如果你不想经过 FastAPI service，可以直接用 `loader.get_view(...).query(...)`：

```python
import sys
sys.path.insert(0, "src")

import asyncio
from pathlib import Path

from datacloud_data_sdk import InvocationContext, OntologyLoader
from datacloud_data_sdk.ontology.term_loader import TermLoader
from datacloud_data_sdk.plan.query_plan_generator import LangGraphPlanGenerator


async def main() -> None:
    loader = OntologyLoader()
    loader.load_from_path("resources/ontology/crm_demo/objects_registry.json")
    loader.load_scene_from_path("resources/ontology/crm_demo/views/scene_01_data_analysis.json")
    loader.configure(
        plan_generator=LangGraphPlanGenerator(
            model="gpt-4o",
            base_url="https://api.openai.com/v1",
            api_key="your-api-key",
            temperature=0.0,
            max_retries=2,
        ),
        term_loader=TermLoader.from_config({}),
        csv_base_dir=str(Path("./tmp").resolve()),
        sql_execution_mode="internal",
    )

    view = loader.get_view("scene_01_data_analysis")
    with InvocationContext(tenant_id="t1", user_id="u1"):
        result = await view.query("按部门统计本月销售商机金额", include_plan=True)

    print(result)


asyncio.run(main())
```

这个用例适合验证跨对象查询，因为 `scene_01_data_analysis` 视图会聚合多个对象和它们之间的关系。

### SDK 查询对象动作并执行

```python
import sys
sys.path.insert(0, "src")

import asyncio

from datacloud_data_sdk import OntologyLoader


async def main() -> None:
    loader = OntologyLoader()
    loader.load_from_path("resources/ontology/crm_demo/objects_registry.json")

    obj = loader.get_object("todo_items")

    print("actions:", obj.list_action_codes())
    print("schema:", obj.get_action_schema("query_todo_list"))

    result = await obj.invoke_action(
        "query_todo_list",
        {
            "status": "PENDING",
            "page": "1",
            "pageSize": "10",
            "keyword": "审批",
        },
    )
    print(result)


asyncio.run(main())
```

说明：

- 这个用例不走 Agent 规划，而是直接走动作执行链路
- `todo_items.query_todo_list` 是本体里定义的 `query` 动作，会根据 `function_refs` 调对应 API
- 执行前需要确保动作对应的 HTTP 服务可访问

### SDK 通过视图调用对象动作

```python
import sys
sys.path.insert(0, "src")

import asyncio

from datacloud_data_sdk import OntologyLoader


async def main() -> None:
    loader = OntologyLoader()
    loader.load_from_path("resources/ontology/crm_demo/objects_registry.json")
    loader.load_scene_from_path("resources/ontology/crm_demo/views/scene_01_data_analysis.json")

    view = loader.get_view("scene_01_data_analysis")
    result = await view.invoke_object_action(
        "todo_items",
        "query_todo_list",
        {
            "status": "PENDING",
            "page": "1",
            "pageSize": "10",
        },
    )
    print(result)


asyncio.run(main())
```

可用函数：

- `loader.get_object(object_code)`：获取单个对象
- `loader.get_view(view_id)`：获取预定义视图
- `await obj.query(question, include_plan=True)`：直接按对象查询
- `await view.query(question, include_plan=True)`：直接按视图查询
- `obj.list_action_codes()`：列出对象可执行动作
- `obj.get_action_schema(action_code)`：查看动作参数 schema
- `await obj.invoke_action(action_code, params)`：直接执行对象动作
- `await view.invoke_object_action(object_code, action_code, params)`：通过视图调用对象动作

补充说明：

- `LangGraphPlanGenerator(...)` 对齐 service 的 NL2SQL 计划生成方式
- `TermLoader.from_config({})` 对齐 service 的术语加载方式，固定使用知识库术语加载器
- Service 启动时还会自动为 DB / KB 对象注入 `query_{object_code}` 这类虚拟查询动作

查询结果为普通 Python `dict`，通常包含：

- `records`
- `meta`
- `plan`（当 `include_plan=True` 时）

### REST API 用法

```bash
# 1. 视图查询：真实走 Agent 规划
curl --location --request POST 'http://localhost:8080/api/v1/query' \
--header 'Content-Type: application/json' \
--header 'X-Tenant-Id: tenant-001' \
--header 'X-User-Id: user-001' \
--header 'X-Session-Id: session-001' \
--header 'Authorization: Bearer your-token' \
--header 'X-System-Code: crm' \
--data-raw '{
  "question": "按部门统计本月销售商机金额",
  "view_id": "scene_01_data_analysis"
}'

# 2. 对象查询：真实走 Agent 规划
curl --location --request POST 'http://localhost:8080/api/v1/query' \
--header 'Content-Type: application/json' \
--header 'X-Tenant-Id: tenant-001' \
--header 'X-User-Id: user-001' \
--data-raw '{
  "question": "查询最近30天商机列表",
  "object_ids": ["sales_business_opportunity"]
}'

# 3. 查看某个对象范围内可用的工具 / 动作
curl -X POST http://localhost:8080/api/v1/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-Tenant-Id: t1" \
  -H "X-Tool-List-Mode: per_object" \
  -H "X-Object-Ids: todo_items" \
  -d '{"jsonrpc":"2.0","id":"1","method":"tools/list","params":{}}'

# 4. 调用对象动作
curl -X POST http://localhost:8080/api/v1/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-Tenant-Id: t1" \
  -d '{
    "jsonrpc":"2.0",
    "id":"2",
    "method":"tools/call",
    "params":{
      "name":"query_todo_list",
      "arguments":{
        "status":"PENDING",
        "page":"1",
        "pageSize":"10"
      }
    }
  }'

# 5. 获取指定视图或对象集合的技能包 / 工具定义
curl -X GET "http://localhost:8080/api/v1/skills/package?view_id=scene_01_data_analysis" \
  -H "X-Tenant-Id: t1"
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
