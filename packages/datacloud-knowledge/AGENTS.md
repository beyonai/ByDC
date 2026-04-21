# AGENTS.md

**Package:** datacloud-knowledge
**Version:** 0.2.0
**Python:** >=3.12
**工具链:** uv + ruff + mypy

---

## Overview

知识服务 SDK — 术语检索、意图消歧、本体查询、N跳子图查询。
将自然语言转化为结构化查询计划，支持多 schema 隔离。

## Structure

```
packages/datacloud-knowledge/
├── src/datacloud_knowledge/
│   ├── db/                    # DB 基础设施（连接、schema 上下文、ORM）
│   ├── intent/                # 意图识别（消歧、召回、澄清、评分）
│   │   └── clarification/     # 多轮澄清子模块
│   ├── query/                 # NL→SQL 图查询、模糊匹配
│   │   ├── search/            # BM25/向量/子串召回
│   │   ├── fuzzy/             # RapidFuzz 模糊匹配
│   │   └── embedding/         # 向量嵌入服务
│   ├── knowledge_build/       # 知识构建（OWL 导入）
│   │   └── importer/          # 导入管线（解析→转换→写入）
│   ├── knowledge_search/      # 知识检索、OWL 关系解析
│   ├── owl_gen/               # OWL 文件生成（表→OWL）
│   └── file_store/            # 文件存储（S3/本地）
├── db/                        # 数据库资产
│   ├── ddl/whale_datacloud/   # 建表 DDL（完整表结构）
│   ├── migrations/            # 存量库增量迁移
│   ├── data_fixes/            # 数据修复脚本
│   ├── seed/                  # 种子数据（幂等）
│   └── scripts/               # 初始化/校验脚本
├── tests/                     # pytest 测试
└── scripts/manual/            # 手动评测脚本
```

## Where to Look

| Task | Location |
|------|----------|
| 自然语言→语义树 | `query/sql_engine.py:SQLKnowledgeGraphQuery.query()` |
| 术语提取（双向最大匹配） | `query/sql_engine.py:extract_entities()` |
| BM25/向量/子串召回 | `query/search/bm25.py`, `vector.py`, `substring_recall.py` |
| 模糊匹配 | `query/fuzzy/rapidfuzz_matcher.py` |
| 意图消歧 | `intent/disambiguation.py:disambiguate_with_session()` |
| 多轮澄清 | `intent/clarification/api.py` |
| 术语召回 | `intent/batch_recall.py`, `intent/typed_recall.py` |
| OWL 导入 | `knowledge_build/importer/runner.py` → `executor.py` → `writer.py` |
| DB 连接/schema | `db/context.py:DatabaseContext`, `db/connection.py:get_session()` |
| 文件上传/下载 | `file_store/manager.py:FileManager` |
| 数据库 DDL | `db/ddl/whale_datacloud/*.sql` |
| OWL 生成 | `owl_gen/generator.py:generate()` |

## Code Map

| Symbol | Type | Location | Role |
|--------|------|----------|------|
| `SQLKnowledgeGraphQuery` | Class | `query/sql_engine.py` (1677L) | 主查询服务（单例） |
| `VocabularyCache` | Class | `query/vocab_cache.py` | 术语缓存 |
| `ParadigmResolutionState` | Class | `intent/paradigm_builder.py` | 范式解析状态机 |
| `DatabaseContext` | Class | `db/context.py` | Schema 隔离（SET LOCAL search_path） |
| `FileManager` | Class | `file_store/manager.py` | 文件存储抽象 |
| `run()` | Function | `knowledge_build/importer/runner.py` | OWL 导入入口 |
| `get_session()` | Function | `db/connection.py` | SQLAlchemy Session 上下文管理器 |
| `resolve_knowledge_schema()` | Function | `db/url.py` | 读取 DATACLOUD_DB_SCHEMA 环境变量 |

## DB 架构

- **驱动**: psycopg3（原生）+ SQLAlchemy 2.0（ORM）
- **Schema 隔离**: `DatabaseContext` 在事务开始时执行 `SET LOCAL search_path TO <schema>`
- **默认 schema**: `whale_datacloud`（通过 `DATACLOUD_DB_SCHEMA` 环境变量覆盖）
- **连接方式**: importer 用 psycopg3 原生连接；intent/query/search 用 SQLAlchemy Session
- **OpenGauss 兼容**: `db/connection.py` 含 PGDialect 补丁

---

## 工具链

| 用途 | 工具 | 命令 |
|------|------|------|
| 包管理 | `uv` | `uv sync` |
| 格式化 | `ruff format` | `uv run ruff format .` |
| Lint | `ruff check` | `uv run ruff check .` |
| 类型检查 | `mypy` | `uv run mypy .` |
| 测试 | `pytest` | `uv run pytest` |

## 规范

- Python >= 3.12，`uv` + `pyproject.toml`
- Ruff: 行宽 100，双引号，4 空格缩进
- MyPy strict mode，`# type: ignore` 必须带错误码
- Commit 格式（中文）：`<type>(<scope>): <描述>`
- 一个 commit 一个逻辑变更，实现与测试一起提交

## Anti-Patterns

- ❌ `from ... import *` — 禁用通配符导入
- ❌ `# type: ignore` 不带错误码
- ❌ `as any` — 禁用类型抑制
- ❌ `eval()`, `exec()` — 禁用动态代码执行
- ❌ 裸 `except:` — 必须指定异常类型
- ❌ `print()` 生产代码 — 用 `logging`
- ❌ SQL 中硬编码 `whale_datacloud.` — 用 `DatabaseContext` + `search_path`

## Commands

```bash
# 安装依赖（从项目根目录）
uv sync

# 格式化 + Lint
uv run ruff format packages/datacloud-knowledge/
uv run ruff check packages/datacloud-knowledge/

# 类型检查
uv run mypy packages/datacloud-knowledge/src/

# 运行测试
uv run pytest packages/datacloud-knowledge/tests/
uv run pytest -m db_integration  # 数据库集成测试

# 数据库初始化
python db/scripts/apply_whale_datacloud.py
```

## Notes

- **单例服务**: `get_singleton_service()` 返回全局实例，测试用 `reset_singleton_service()` 重置
- **数据库测试**: 需要 `DATACLOUD_ENABLE_INTEGRATION_TESTS=1` + DB 环境变量
- **Re-export shim**: `db_url.py` 和 `knowledge_search/db/` 保留向后兼容 shim，新代码应从 `db/` 导入
- **TODO(ontology)**: `intent/clarification/api.py` 有待实现的 ontology_code 过滤