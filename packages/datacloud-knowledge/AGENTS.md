# AGENTS.md

**Package:** datacloud-knowledge
**Version:** 0.2.0
**Python:** >=3.12
**工具链:** uv + ruff + mypy

---

## Overview

知识服务 SDK — 术语检索、本体查询、N跳子图查询。
将自然语言转化为结构化查询计划。

## Structure

```
packages/datacloud-knowledge/
├── src/datacloud_knowledge/   # SDK 主包
│   ├── query/                 # NL→SQL 图查询、模糊匹配
│   ├── knowledge_build/       # 术语构建（本体/枚举/列表/导入）
│   ├── knowledge_search/      # 知识检索、OWL关系解析
│   └── file_store/            # 文件存储（S3/本地）
├── db/                        # 数据库资产（DDL/Seed/脚本）
└── tests/                     # pytest 测试
```

## Where to Look

| Task | Location |
|------|----------|
| 自然语言→语义树 | `query/sql_engine.py:SQLKnowledgeGraphQuery.query()` |
| 术语提取（正向/逆向最大匹配） | `query/sql_engine.py:extract_entities()` |
| 模糊匹配 | `query/fuzzy/rapidfuzz_matcher.py` |
| OWL 导入 | `knowledge_build/importer/executor.py` |
| 文件上传/下载 | `file_store/manager.py:FileManager` |
| 数据库 DDL | `db/ddl/whale_datacloud/*.sql` |

## Code Map

| Symbol | Type | Location | Role |
|--------|------|----------|------|
| `SQLKnowledgeGraphQuery` | Class | `query/sql_engine.py` | 主查询服务（单例模式） |
| `TreeNode` | Class | `query/sql_engine.py` | 语义树节点 |
| `FileManager` | Class | `file_store/manager.py` | 文件存储抽象 |
| `VocabularyCache` | Class | `query/vocab_cache.py` | 术语缓存 |
| `run()` | Function | `knowledge_build/importer/runner.py` | OWL 导入入口 |

---

## 工具链 (2026)

| 用途 | 工具 | 命令 |
|------|------|------|
| 包管理 | `uv` | `uv sync` |
| 格式化 | `ruff format` | `uv run ruff format .` |
| Lint | `ruff check` | `uv run ruff check .` |
| 类型检查 | `mypy` | `uv run mypy .` |
| 测试 | `pytest` | `uv run pytest` |

---

## 规范

### Python 环境
- 使用 `uv` + `pyproject.toml` 管理依赖
- Python >= 3.12

### 代码风格
- **Ruff** 格式化 + Lint（企业级配置）
- 行宽 100，双引号，4 空格缩进
- 启用规则: E, F, I, N, W, UP, B, C4, SIM, ASYNC, S, DTZ, LOG, PTH, RET, TRY, TC, PL, PERF 等

### 类型检查
- **MyPy strict mode**
- 必须带类型注解
- `# type: ignore` 必须带错误码

### 文档编写
- **SSOT 原则**：单一事实来源，引用代替抄写
- DRY：任何实体/接口/字段全局只定义一次

### Git Workflow

**Commit 格式（中文）：**
```
<type>(<scope>): <描述>

types: feat / fix / docs / style / refactor / test / chore
```

**Atomic Commits:**
- 一个 commit 一个逻辑变更
- 实现与测试一起提交

---

## Anti-Patterns

- ❌ `from ... import *` — 禁用通配符导入
- ❌ `# type: ignore` 不带错误码
- ❌ `as any` — 禁用类型抑制
- ❌ `eval()`, `exec()` — 禁用动态代码执行
- ❌ 裸 `except:` — 必须指定异常类型
- ❌ `print()` 生产代码 — 用 `logging`

---

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

---

## Notes

- **单例服务**：`get_singleton_service()` 返回全局实例，测试用 `reset_singleton_service()` 重置
- **数据库测试**：需要设置 `DATACLOUD_ENABLE_INTEGRATION_TESTS=1` 和 DB 环境变量