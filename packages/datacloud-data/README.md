# datacloud-data

[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Apache--2.0-green.svg)](https://www.apache.org/licenses/LICENSE-2.0)
[![Code style](https://img.shields.io/badge/code%20style-ruff-black.svg)](https://docs.astral.sh/ruff/)

`datacloud-data` 是 DataCloud 的数据服务与 SDK 包。它负责加载本体资源、生成查询计划，
执行跨数据源动作，并通过 Python SDK、REST API、MCP Tools 和 GraphQL 暴露统一的数据访问能力。

## 功能特性

- 支持从 JSON、YAML、OWL 资源加载对象、关系、动作和视图定义。
- 配置 LLM 后可通过 `LangGraphPlanGenerator` 生成自然语言查询计划。
- 支持 SQL、API、知识库和虚拟动作等执行方式。
- 提供 FastAPI 服务，包含 `/api/v1/query`、`/api/v1/mcp`、`/api/v1/skills`、
  `/api/v1/health`，以及可选 `/graphql` 路由。
- 支持参数归一、逻辑参数到物理请求体映射、响应字段抽取、术语值转换和结果溢出导出。

## 参数与结果转换

- 入参会做基础类型归一，常见字符串值可自动转成数值、布尔值和日期类型。
- 动作调用支持逻辑参数到物理请求体的映射，API 返回也会按映射规则抽取为统一结果。
- 查询结果会做术语值转换，并在需要时自动导出 CSV 预览文件。

## 环境要求

- Python `>=3.12`
- 本地开发推荐使用 `uv`
- 按需安装数据库、服务和知识库相关扩展依赖

## 安装

在仓库根目录安装：

```bash
uv sync
uv pip install -e "packages/datacloud-data[all]"
```

在子包目录安装：

```bash
cd packages/datacloud-data
uv venv .venv --python 3.12
uv pip install -e ".[all]"
```

可选依赖：

| Extra | 说明 |
| --- | --- |
| `langchain` | LangGraph 与 LangChain OpenAI 查询规划能力 |
| `sql` | SQLAlchemy 与关系型数据库连接器 |
| `clickhouse` | ClickHouse 异步连接器 |
| `service` | FastAPI、Uvicorn、MCP、GraphQL 与服务运行时依赖 |
| `knowledge` | `datacloud-knowledge` 集成 |
| `all` | SDK 与服务常用运行时依赖 |
| `dev` | 测试、Lint 与类型检查依赖 |

## 快速开始

使用包内 OWL 示例资源启动本地服务：

```bash
DATACLOUD_ONTOLOGY_PATH=packages/datacloud-data/resources \
uv run uvicorn datacloud_data_service.api.routes:create_app \
  --factory \
  --host 0.0.0.0 \
  --port 8080
```

验证服务状态：

```bash
curl http://localhost:8080/api/v1/health
curl http://localhost:8080/api/v1/loader/status
```

运行 SDK 示例：

```bash
cd packages/datacloud-data
PYTHONPATH=src uv run python examples/all_interfaces_example.py
```

## 配置

在 `packages/datacloud-data` 目录下复制环境变量模板：

```bash
cp .env.example .env
```

服务会读取 `packages/datacloud-data/.env` 和
`packages/datacloud-data/src/datacloud_data_service/.env`。相对路径会按仓库根目录解析。

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DATACLOUD_ONTOLOGY_PATH` | `resources/ontology/crm_demo/objects_registry.json` | JSON、YAML、OWL 文件或资源目录。包内 OWL 示例可使用 `packages/datacloud-data/resources`。 |
| `DATACLOUD_LLM_API_KEY` | 空 | 配置后启用 LLM 查询计划生成；为空时自然语言规划不可用。 |
| `DATACLOUD_LLM_API_BASE` | 空 | LLM API 地址。 |
| `DATACLOUD_LLM_MODEL` | `gpt-4o` | LLM 模型名称。 |
| `DATACLOUD_LLM_TEMPERATURE` | `0.0` | LLM 温度参数。 |
| `DATACLOUD_CSV_BASE_DIR` | `./tmp` | 中间 CSV 输出目录。 |
| `DATACLOUD_RESULT_FILE_STORAGE_TYPE` | `local` | 结果文件存储后端。 |
| `DATACLOUD_RESULT_FILE_BASE_DIR` | `./tmp` | 本地结果文件目录。 |
| `DATACLOUD_QUERY_RESULT_CSV_THRESHOLD` | `5` | 查询结果超过该行数时写入 CSV。 |
| `DATACLOUD_SQL_EXECUTION_MODE` | `internal` | SQL 执行模式。 |
| `DATACLOUD_TRACE_ENABLED` | `false` | 是否启用查询链路日志。 |
| `DATACLOUD_TRACE_LOG_PATH` | `logs/query_trace.log` | 查询链路日志路径。 |
| `DATACLOUD_LOADER_MODE` | `watch` | Loader 刷新模式：`watch`、`lazy`、`static`。 |
| `DATACLOUD_CORS_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | CORS 允许来源，多个值用逗号分隔。 |
| `DATACLOUD_VIRTUAL_ACTION_QUERY_PREFIX` | `query_` | 生成查询动作的名称前缀。 |
| `DATACLOUD_VIRTUAL_ACTION_COMPUTE_PREFIX` | `compute_` | 生成计算动作的名称前缀。 |

数据源通常从本体对象的 `source_config` 中加载，也可以参考
`config/datasources.yaml.example` 使用 YAML 配置。

## Python SDK

不依赖外部 LLM 的最小示例：

```python
from __future__ import annotations

import asyncio

from datacloud_data_sdk import InvocationContext, OntologyLoader
from datacloud_data_sdk.plan.query_plan_generator import MockPlanGenerator
from datacloud_data_sdk.sql_executor.models import DataSourceConfig

REGISTRY = {
    "functions": [],
    "objects": [
        {
            "object_code": "sales_bo",
            "object_name": "销售商机",
            "description": "商机对象",
            "source_type": "DB",
            "source_config": {
                "alias": "test_db",
                "db_type": "SQLITE",
                "jdbc_url": "jdbc:sqlite::memory:",
            },
            "datasource_alias": "test_db",
            "table_name": "sales_bo",
            "fields": [
                {"field_code": "bo_id", "field_name": "商机ID", "field_type": "STRING"},
                {"field_code": "bo_name", "field_name": "商机名称", "field_type": "STRING"},
            ],
            "actions": [],
        }
    ],
    "relations": [],
}

PLAN = {
    "can_answer": True,
    "steps": [
        {
            "step_id": "s1",
            "type": "SQL",
            "source_id": "SRC_TEST_DB",
            "datasource_alias": "test_db",
            "sql_template": "SELECT '1' AS bo_id, '项目A' AS bo_name",
            "output_ref": "bo_list",
        }
    ],
    "aggregation": {
        "strategy": "DIRECT",
        "final_step_id": "s1",
        "columns": [
            {"name": "bo_id", "label": "商机ID", "type": "string"},
            {"name": "bo_name", "label": "商机名称", "type": "string"},
        ],
    },
}


async def main() -> None:
    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    loader.configure(
        plan_generator=MockPlanGenerator(fixed_plan=PLAN),
        datasource_configs={
            "test_db": DataSourceConfig(
                alias="test_db",
                db_type="SQLITE",
                jdbc_url="jdbc:sqlite::memory:",
            )
        },
        csv_base_dir="./tmp",
    )

    obj = loader.get_object("sales_bo")
    with InvocationContext(tenant_id="t1", user_id="u1"):
        result = await obj.query("查商机", include_plan=True)

    records = result.get("records", [])
    assert records == [{"bo_id": "1", "bo_name": "项目A"}]


asyncio.run(main())
```

需要真实自然语言规划时，配置 `DATACLOUD_LLM_*` 后将 `MockPlanGenerator` 替换为
`LangGraphPlanGenerator`。

### 运行完整示例

```bash
cd packages/datacloud-data
PYTHONPATH=src uv run python examples/all_interfaces_example.py
```

### SDK 常用入口

| 方法 | 说明 |
| --- | --- |
| `loader.get_object(object_code)` | 获取单个对象。 |
| `loader.get_view(view_id)` | 获取预定义视图。 |
| `await obj.query(question, include_plan=True)` | 按对象执行自然语言查询。 |
| `await view.query(question, include_plan=True)` | 按视图执行自然语言查询。 |
| `obj.list_action_codes()` | 列出对象可执行动作。 |
| `obj.get_action_schema(action_code)` | 查看动作参数 Schema。 |
| `await obj.invoke_action(action_code, params)` | 直接执行对象动作。 |
| `await view.invoke_object_action(object_code, action_code, params)` | 通过视图调用对象动作。 |

### SDK 按对象查询

适合问题只涉及单个对象的场景。`LangGraphPlanGenerator` 会真实调用 LLM 生成查询计划。

```python
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from datacloud_data_sdk import InvocationContext, OntologyLoader
from datacloud_data_sdk.ontology.term_loader import TermLoader
from datacloud_data_sdk.plan.query_plan_generator import LangGraphPlanGenerator


async def main() -> None:
    loader = OntologyLoader()
    loader.load_from_owl_resource_directory(os.environ["DATACLOUD_ONTOLOGY_PATH"])
    loader.configure(
        plan_generator=LangGraphPlanGenerator(
            model=os.environ.get("DATACLOUD_LLM_MODEL", "gpt-4o"),
            base_url=os.environ["DATACLOUD_LLM_API_BASE"],
            api_key=os.environ["DATACLOUD_LLM_API_KEY"],
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

    records = result.get("records", [])
    plan = result.get("plan", {})
    assert isinstance(records, list)
    assert plan


asyncio.run(main())
```

### SDK 按视图查询

视图查询适合跨对象、跨关系的分析问题。需要先加载对象注册表，再加载视图定义。

```python
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from datacloud_data_sdk import InvocationContext, OntologyLoader
from datacloud_data_sdk.ontology.term_loader import TermLoader
from datacloud_data_sdk.plan.query_plan_generator import LangGraphPlanGenerator


async def main() -> None:
    loader = OntologyLoader()
    loader.load_from_owl_resource_directory(os.environ["DATACLOUD_ONTOLOGY_PATH"])
    loader.configure(
        plan_generator=LangGraphPlanGenerator(
            model=os.environ.get("DATACLOUD_LLM_MODEL", "gpt-4o"),
            base_url=os.environ["DATACLOUD_LLM_API_BASE"],
            api_key=os.environ["DATACLOUD_LLM_API_KEY"],
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

    records = result.get("records", [])
    assert isinstance(records, list)


asyncio.run(main())
```

### SDK 执行对象动作

动作调用不经过 LLM 规划，适合直接调用本体中定义的 API、脚本或虚拟动作。

```python
from __future__ import annotations

import asyncio
import os

from datacloud_data_sdk import InvocationContext, OntologyLoader


async def main() -> None:
    loader = OntologyLoader()
    loader.load_from_owl_resource_directory(os.environ["DATACLOUD_ONTOLOGY_PATH"])

    obj = loader.get_object("todo_items")
    action_codes = obj.list_action_codes()
    schema = obj.get_action_schema("query_todo_list")
    assert "query_todo_list" in action_codes
    assert schema

    with InvocationContext(tenant_id="t1", user_id="u1"):
        result = await obj.invoke_action(
            "query_todo_list",
            {
                "status": "PENDING",
                "page": "1",
                "pageSize": "10",
                "keyword": "审批",
            },
        )

    assert isinstance(result, dict)


asyncio.run(main())
```

### SDK 通过视图调用对象动作

当上层只持有视图上下文时，可以通过视图转发到指定对象动作。

```python
from __future__ import annotations

import asyncio
import os

from datacloud_data_sdk import InvocationContext, OntologyLoader


async def main() -> None:
    loader = OntologyLoader()
    loader.load_from_owl_resource_directory(os.environ["DATACLOUD_ONTOLOGY_PATH"])

    view = loader.get_view("scene_01_data_analysis")
    with InvocationContext(tenant_id="t1", user_id="u1"):
        result = await view.invoke_object_action(
            "todo_items",
            "query_todo_list",
            {
                "status": "PENDING",
                "page": "1",
                "pageSize": "10",
            },
        )

    assert isinstance(result, dict)


asyncio.run(main())
```

## REST API

查询已加载的本体资源：

```bash
curl -X POST http://localhost:8080/api/v1/query \
  -H "Content-Type: application/json" \
  -H "X-Tenant-Id: tenant-001" \
  -H "X-User-Id: user-001" \
  -d '{
    "question": "查询项目列表",
    "object_ids": ["by_project"]
  }'
```

列出某个对象范围内的 MCP Tools：

```bash
curl -X POST http://localhost:8080/api/v1/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-Tenant-Id: tenant-001" \
  -H "X-Object-Ids: by_project" \
  -d '{"jsonrpc":"2.0","id":"1","method":"tools/list","params":{}}'
```

获取生成的技能包：

```bash
curl -X GET "http://localhost:8080/api/v1/skills/package?object_ids=by_project" \
  -H "X-Tenant-Id: tenant-001"
```

## 目录结构

```text
packages/datacloud-data/
├── config/                         # 数据源配置示例
├── docs/                           # 设计文档与实施计划
├── examples/                       # 可运行 SDK 示例
├── resources/                      # 包内 OWL 对象与视图资源
├── scripts/                        # 导入、导出与迁移脚本
├── src/
│   ├── datacloud_data_sdk/
│   │   ├── agents/                 # LLM Agent
│   │   ├── aggregator/             # 结果聚合
│   │   ├── csv_storage/            # CSV 大文件存储
│   │   ├── events/                 # 事件总线与追踪
│   │   ├── executor/               # 查询与动作执行器
│   │   ├── file_storage/           # 本地结果文件存储
│   │   ├── graphql/                # GraphQL 支持
│   │   ├── ontology/               # 本体加载与解析
│   │   ├── oql/                    # OQL 适配与路由
│   │   ├── plan/                   # 查询计划生成与校验
│   │   ├── sql_executor/           # SQL 执行与连接器
│   │   ├── utils/                  # 通用工具函数
│   │   └── virtual_action/         # 虚拟动作生成与校验
│   └── datacloud_data_service/
│       ├── api/                    # REST、MCP 与 GraphQL 路由
│       └── tools/                  # MCP 工具与技能包生成
└── tests/                          # 单元测试与集成测试
```

## 许可证

Apache License 2.0。详见仓库许可证文件。
