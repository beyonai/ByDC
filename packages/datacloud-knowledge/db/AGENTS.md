# AGENTS.md

**Module:** db
**Purpose:** 数据库资产管理 — DDL/Seed/迁移/脚本

---

## Overview

自包含的数据库资产管理：完整建表 DDL、增量迁移、种子数据、数据修复脚本、ER 图。

## Structure

```
db/
├── er/                         # ER 图（Mermaid）
├── ddl/whale_datacloud/        # 建表 DDL（完整表结构，00~99 顺序执行）
│   ├── 00_create_schema.sql    # DROP + CREATE SCHEMA（破坏性）
│   ├── 01~08_*.sql             # 各表建表语句
│   └── 99_indexes_constraints.sql
├── migrations/                 # 存量库增量迁移（幂等，IF NOT EXISTS）
│   ├── 97_add_code_columns.sql
│   ├── 98_add_ext_attrs.sql
│   ├── 98_add_term_name_search.sql  # BM25 + 向量列 + 触发器
│   ├── 98_add_term_name_tags.sql    # search_scope 列
│   └── 98_alter_term_id_length.sql
├── data_fixes/                 # 数据修复/同步脚本（非 DDL）
│   └── 99_sync_ontology_ext_attrs.sql
├── seed/whale_datacloud/       # 种子数据（ON CONFLICT DO NOTHING）
│   └── 01_term_type_builtin.sql
└── scripts/
    ├── apply_whale_datacloud.py   # 执行 DDL → Seed
    └── verify_whale_datacloud.py  # 校验表结构
```

## Where to Look

| Task | Location |
|------|----------|
| 初始化数据库 | `scripts/apply_whale_datacloud.py` |
| 校验表结构 | `scripts/verify_whale_datacloud.py` |
| ER 图 | `er/whale_datacloud.mmd` |
| 存量库升级 | `migrations/98_*.sql` |
| 本体冗余同步 | `data_fixes/99_sync_ontology_ext_attrs.sql` |

## Execution Order

| Phase | Directory | Notes |
|-------|-----------|-------|
| DDL | `ddl/whale_datacloud/` | `00_` 自动提交（DROP），其余事务内 |
| Migrations | `migrations/` | 存量库增量，幂等，新建库无需执行 |
| Seed | `seed/whale_datacloud/` | `ON CONFLICT DO NOTHING` 幂等 |
| Data Fixes | `data_fixes/` | 按需手动执行 |

## Commands

```bash
python db/scripts/apply_whale_datacloud.py            # DDL + Seed
python db/scripts/apply_whale_datacloud.py --seed-only # 仅 Seed
python db/scripts/verify_whale_datacloud.py            # 校验
pytest tests/db/test_schema_apply.py                   # 测试
```

## Environment

```bash
export DATACLOUD_DB_HOST=localhost
export DATACLOUD_DB_PORT=15432
export DATACLOUD_DB_USER=postgres
export DATACLOUD_DB_PASSWORD=your_password
export DATACLOUD_DB_DATABASE=your_database
export DATACLOUD_DB_SCHEMA=whale_datacloud  # 可选，默认 whale_datacloud
```

## Notes

- **DDL 有破坏性**: `00_create_schema.sql` 会 DROP 旧表
- **Seed 幂等**: 可重复执行
- **DDL 已包含完整列**: `06_term_name.sql` 含 search_scope/name_keywords/name_embedding/name_keywords_jieba
- 生产环境仅首次初始化执行 DDL；存量库用 `migrations/` 增量升级