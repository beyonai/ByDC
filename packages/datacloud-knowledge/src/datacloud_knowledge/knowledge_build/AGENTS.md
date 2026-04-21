# AGENTS.md

**Module:** knowledge_build
**Purpose:** 知识构建 — OWL 导入管线 + FastAPI 路由

---

## Overview

OWL 格式知识包的导入管线：解析→转换→预检→批量写入 DB→回调通知。

## Structure

```
knowledge_build/
├── importer/              # OWL 导入管线（核心）
│   ├── runner.py          # 入口：预检→入库→回调
│   ├── executor.py        # 编排层：连接、路由分发、schema 设置
│   ├── writer.py          # SQL 写入层：6 个 _batch_process_* 函数（728L）
│   ├── _helpers.py        # 共享工具：_execute_values、ID 查找等
│   ├── owl_parser.py      # OWL XML 解析
│   ├── owl_converter.py   # OWL→内部格式转换
│   ├── precheck.py        # 导入前全量校验
│   ├── snowflake.py       # 雪花 ID 生成
│   └── notifier.py        # 回调通知
├── router.py              # FastAPI 路由（/build/import-package/*）
└── schema.py              # Pydantic 请求/响应模型
```

## Where to Look

| Task | Location |
|------|----------|
| OWL 导入入口 | `importer/runner.py:run()` |
| 编排 + schema 设置 | `importer/executor.py:run()` |
| 批量 SQL 写入 | `importer/writer.py:_batch_process_*()` |
| 共享工具函数 | `importer/_helpers.py` |
| OWL 解析 | `importer/owl_parser.py` |
| 数据转换 | `importer/owl_converter.py` |
| 预检查 | `importer/precheck.py` |

## Import Flow

```
OWL 文件
  → owl_parser.py (XML 解析)
  → owl_converter.py (转换为内部格式)
  → precheck.py (全量校验)
  → executor.py (SET LOCAL search_path + 路由分发)
  → writer.py (批量写入 DB，裸表名)
  → notifier.py (回调通知)
```

## Conventions

- **Schema 隔离**: `executor.py` 通过 `DatabaseContext` + `SET LOCAL search_path` 注入 schema
- **SQL 裸表名**: `writer.py` 中所有 SQL 使用裸表名，不硬编码 schema
- **批量写入**: `_execute_values()` 模拟 psycopg2 的 execute_values（psycopg3 兼容）
- **幂等导入**: UPSERT 模式，支持 add/update/delete 操作
- **事务管理**: 整个导入在单事务内，失败整体回滚

## Notes

- `writer.py` 728 行 — 6 个实体的批量处理逻辑
- `_helpers.py` 被 executor.py 和 writer.py 共享，避免循环导入
- 导入前必须运行 `db/scripts/apply_whale_datacloud.py` 初始化表结构