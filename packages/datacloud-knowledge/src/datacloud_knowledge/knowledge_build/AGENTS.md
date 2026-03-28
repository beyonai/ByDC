# AGENTS.md

**Module:** knowledge_build
**Purpose:** 知识构建 — 本体/枚举/列表术语管理与导入

---

## Overview

术语生命周期管理：构建、更新、导入（OWL 格式）。支持本体术语、枚举术语、列表术语三种类型。

## Structure

```
knowledge_build/
├── importer/          # OWL 导入（核心）
│   ├── executor.py    # 批量执行器（1127 行）
│   ├── owl_parser.py  # OWL 解析
│   ├── owl_converter.py # 数据转换
│   ├── precheck.py    # 预检查
│   ├── runner.py      # 入口
│   └── snowflake.py   # ID 生成
├── ontology/          # 本体术语
├── enum_term/         # 枚举术语
├── list_term/         # 列表术语
└── schema.py          # Pydantic 模型
```

## Where to Look

| Task | Location |
|------|----------|
| OWL 导入入口 | `importer/runner.py:run()` |
| 批量处理逻辑 | `importer/executor.py:run()` |
| OWL 解析 | `importer/owl_parser.py` |
| 数据转换 | `importer/owl_converter.py` |
| 预检查 | `importer/precheck.py` |

## Import Flow

```
OWL 文件
  → owl_parser.py (解析)
  → owl_converter.py (转换为内部格式)
  → precheck.py (校验)
  → executor.py (批量写入 DB)
  → notifier.py (回调通知)
```

## Conventions

- **批量写入**：`_execute_values()` 批量 INSERT
- **幂等导入**：UPSERT 模式，支持增量更新
- **事务管理**：DDL 00_ 自动提交，其余事务内执行

## Database Tables

| Table | Purpose |
|-------|---------|
| `term` | 术语主表 |
| `term_relation` | 术语关系 |
| `term_name` | 术语名称（支持别名） |
| `term_vocabulary` | 术语词汇表 |
| `term_knowledge` | 术语知识 |

## Notes

- `executor.py` 1127 行 — 复杂的批量处理逻辑
- 导入前必须运行 `db/scripts/apply_whale_datacloud.py` 初始化表结构