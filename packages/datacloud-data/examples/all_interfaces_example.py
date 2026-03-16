#!/usr/bin/env python
"""datacloud-data-service 全接口可运行用例。

运行方式（在 datacloud-data-service 目录下）：
  PYTHONPATH=src python examples/all_interfaces_example.py

依赖：pip install -e ".[all]"
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# 确保 src 在 path 中
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from datacloud_data_sdk import OntologyLoader, InvocationContext
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

MOCK_PLAN = {
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


async def example_package_sdk() -> None:
    """用例一：Package（SDK）直接调用。"""
    print("\n" + "=" * 60)
    print("【用例一】Package（SDK）直接调用")
    print("=" * 60)

    loader = OntologyLoader()
    loader.load_from_content(REGISTRY)
    loader.configure(
        plan_generator=MockPlanGenerator(fixed_plan=MOCK_PLAN),
        datasource_configs={
            "test_db": DataSourceConfig(
                alias="test_db", db_type="SQLITE", jdbc_url="jdbc:sqlite::memory:"
            )
        },
        csv_base_dir="/tmp/datacloud_csv_example",
    )

    obj = loader.get_object("sales_bo")
    with InvocationContext(tenant_id="t1", user_id="u1"):
        result = await obj.query("查商机", include_plan=True)

    print("records:", result.get("records", []))
    print("plan.can_answer:", result.get("plan", {}).get("can_answer"))


def print_rest_curl() -> None:
    """打印 REST 和 MCP 的 curl 示例（需服务已启动）。"""
    print("\n" + "=" * 60)
    print("【用例二】MCP tools/list 与 tools/call")
    print("=" * 60)
    print("""
# 1. tools/list
curl -X POST http://localhost:8080/api/v1/mcp \\
  -H "Content-Type: application/json" \\
  -H "X-Tenant-Id: t1" \\
  -H "X-User-Id: u1" \\
  -H "Authorization: Bearer tok" \\
  -d '{"jsonrpc":"2.0","id":"1","method":"tools/list","params":{}}'

# 2. tools/call unified_data_query
curl -X POST http://localhost:8080/api/v1/mcp \\
  -H "Content-Type: application/json" \\
  -H "X-Tenant-Id: t1" \\
  -d '{"jsonrpc":"2.0","id":"2","method":"tools/call","params":{"name":"unified_data_query","arguments":{"question":"查商机"}}}'
""")

    print("\n" + "=" * 60)
    print("【用例三】直接 REST 数据查询")
    print("=" * 60)
    print("""
# POST /api/v1/query
curl -X POST http://localhost:8080/api/v1/query \\
  -H "Content-Type: application/json" \\
  -H "X-Tenant-Id: t1" \\
  -H "X-User-Id: u1" \\
  -H "Authorization: Bearer tok" \\
  -d '{"question":"查商机"}'

# GET /api/v1/skills/package
curl -X GET "http://localhost:8080/api/v1/skills/package?object_ids=sales_bo" \\
  -H "X-Tenant-Id: t1"

# GET /health
curl http://localhost:8080/health
""")


async def main() -> None:
    await example_package_sdk()
    print_rest_curl()
    print("\n完整文档见: docs/API_USAGE_EXAMPLES.md")


if __name__ == "__main__":
    asyncio.run(main())
