# 数据库资产（whale_datacloud）

本目录管理 `datacloud-knowledge-service` 的全部数据库资产。

## 目录结构

```
db/
├── er/                         ← ER 关系图（Mermaid 源文件）
├── ddl/whale_datacloud/        ← 建表 DDL（完整表结构），按 00~99 顺序执行
│   ├── 00_create_schema.sql    ← DROP 旧表 + CREATE SCHEMA
│   ├── 01_domain.sql
│   ├── 02_term_library.sql
│   ├── 03_term_type.sql
│   ├── 04_term.sql
│   ├── 05_term_relation.sql
│   ├── 06_term_name.sql        ← 含 search_scope/name_keywords/name_embedding/name_keywords_jieba
│   ├── 07_term_vocabulary.sql
│   ├── 08_term_knowledge.sql
│   └── 99_indexes_constraints.sql
├── migrations/                 ← 存量库增量迁移脚本（幂等，IF NOT EXISTS）
│   ├── 97_add_code_columns.sql
│   ├── 98_add_ext_attrs.sql
│   ├── 98_add_term_name_search.sql
│   ├── 98_add_term_name_tags.sql
│   └── 98_alter_term_id_length.sql
├── data_fixes/                 ← 数据修复/同步脚本（非 DDL）
│   └── 99_sync_ontology_ext_attrs.sql
├── seed/whale_datacloud/       ← 系统预置初始化数据，幂等（ON CONFLICT DO NOTHING）
│   └── 01_term_type_builtin.sql
└── scripts/
    ├── apply_whale_datacloud.py  ← 顺序执行 DDL → Seed
    └── verify_whale_datacloud.py ← 校验表结构是否完整
```

## 执行顺序说明

| 阶段 | 目录 | 说明 |
|------|------|------|
| **DDL** | `ddl/whale_datacloud/` | `00_` 文件先 drop 旧表再建 schema（autocommit）；其余文件在事务内建表，失败回滚 |
| **Migrations** | `migrations/` | 存量库增量迁移，幂等（`IF NOT EXISTS`），新建库无需执行 |
| **Seed** | `seed/whale_datacloud/` | 写入系统预置数据，使用 `ON CONFLICT DO NOTHING` 保证幂等，可重复执行 |
| **Data Fixes** | `data_fixes/` | 数据修复/同步脚本，按需手动执行 |

> **区别**：DDL 每次执行都会重建表（有破坏性），Seed 是幂等的增量写入。
> 生产环境仅首次初始化时执行 DDL；Seed 可随时重跑补数据。
> Migrations 用于已有库的增量升级，新建库的 DDL 已包含完整列定义。

## 环境变量

执行脚本或测试前，设置以下环境变量：

```bash
export DATACLOUD_DB_HOST=localhost
export DATACLOUD_DB_PORT=5432
export DATACLOUD_DB_USER=postgres
export DATACLOUD_DB_PASSWORD=your_password
export DATACLOUD_DB_DATABASE=your_database
# export DATACLOUD_DB_SCHEMA=whale_datacloud  # 可选，默认 whale_datacloud
```

## 应用 DDL + Seed（一键初始化）

```bash
python db/scripts/apply_whale_datacloud.py
```

等价于依次执行：
1. `00_create_schema.sql` → drop 旧表
2. `01~99_*.sql` → 建表 + 索引
3. `seed/01_term_type_builtin.sql` → 写入内置术语类型

## 校验表结构

```bash
python db/scripts/verify_whale_datacloud.py
```

## 运行测试

```bash
pytest tests/db/test_schema_apply.py -q
```
