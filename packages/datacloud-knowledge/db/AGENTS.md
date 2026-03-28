# AGENTS.md

**Module:** db
**Purpose:** 数据库资产管理 — DDL/Seed/脚本

---

## Overview

自包含的数据库资产管理：表结构定义、初始化脚本、种子数据、ER 图。

## Structure

```
db/
├── er/                # ER 图（Mermaid）
├── ddl/whale_datacloud/   # 建表 DDL
│   ├── 00_create_schema.sql   # DROP + CREATE SCHEMA
│   ├── 01_domain.sql
│   ├── 02_term_library.sql
│   ├── 03_term_type.sql
│   ├── 04_term.sql
│   ├── 05_term_relation.sql
│   ├── 06_term_name.sql
│   ├── 07_term_vocabulary.sql
│   ├── 08_term_knowledge.sql
│   └── 99_indexes_constraints.sql
├── seed/whale_datacloud/   # 种子数据（幂等）
└── scripts/
    ├── apply_whale_datacloud.py   # 执行 DDL + Seed
    └── verify_whale_datacloud.py  # 校验表结构
```

## Where to Look

| Task | Location |
|------|----------|
| 初始化数据库 | `scripts/apply_whale_datacloud.py` |
| 校验表结构 | `scripts/verify_whale_datacloud.py` |
| ER 图 | `er/whale_datacloud.mmd` |

## Execution Order

| Phase | Directory | Notes |
|-------|-----------|-------|
| DDL | `ddl/whale_datacloud/` | `00_` 自动提交，其余事务内 |
| Seed | `seed/whale_datacloud/` | `ON CONFLICT DO NOTHING` 幂等 |

## Commands

```bash
# 初始化数据库
python db/scripts/apply_whale_datacloud.py

# 校验表结构
python db/scripts/verify_whale_datacloud.py

# 运行数据库测试
pytest tests/db/test_schema_apply.py
```

## Environment

```bash
export DB_HOST=localhost
export DB_PORT=5432
export DB_USER=postgres
export DB_PASSWORD=your_password
export DB_NAME=your_database
export DB_SCHEMA=whale_datacloud  # 可选
```

## Notes

- **DDL 有破坏性**：`00_create_schema.sql` 会 DROP 旧表
- **Seed 幂等**：可重复执行
- 生产环境仅首次初始化执行 DDL