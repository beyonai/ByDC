# 测试规范 — datacloud-analysis 专项

> **extends**: [`/docs/项目规范/TESTING_CONVENTIONS.md`](../../../docs/项目规范/TESTING_CONVENTIONS.md)（Monorepo 根规范，优先级更高）
>
> **适用范围**：`datacloud-analysis` 子项目，测试目录 `tests/`
>
> **说明**：本文档**仅包含 datacloud-analysis 特有内容**，通用测试规范（命名规则、类型划分、覆盖率方法论等）见根文档。

---

## 1. 测试目录结构

```
tests/
├── datacloud_analysis/                 ← 旧代码备份（只读，禁止新增）
└── datacloud-analysis/                 ← 活跃测试目录（与 src/datacloud_analysis/ 对应）
    ├── conftest.py                  ← 包级公共 fixture（workspace_paths 等）
    ├── unit/
    │   ├── conftest.py              ← unit 专属 fixture（StubSaver、mock_cursor）
    │   ├── test_agent.py
    │   ├── test_bootstrap.py
    │   ├── config/
    │   │   ├── test_env.py
    │   │   └── test_models.py
    │   ├── gateway/
    │   │   ├── test_handler.py
    │   │   └── test_task_adapter.py
    │   ├── memory/
    │   │   ├── test_loader.py
    │   │   └── test_tools.py
    │   ├── orchestration/
    │   │   ├── test_dag.py
    │   │   ├── test_intent.py
    │   │   ├── test_insight.py
    │   │   ├── test_loop.py
    │   │   └── test_sandbox_executor.py
    │   ├── session/
    │   │   ├── test_checkpointer.py
    │   │   ├── test_metadata.py
    │   │   └── test_pg_opengauss.py
    │   ├── skills/
    │   │   ├── test_builtin.py
    │   │   ├── test_group_agg.py
    │   │   └── test_time_series.py
    │   ├── tools/
    │   │   ├── test_data.py
    │   │   ├── test_knowledge.py
    │   │   ├── test_report.py
    │   │   ├── test_sandbox.py
    │   │   └── test_skill.py
    │   └── workspace/
    │       ├── test_mount.py
    │       ├── test_paths.py
    │       └── test_skills_loader.py
    ├── integration/
    │   ├── conftest.py              ← initialized_sdk fixture（需真实 PG）
    │   └── test_bootstrap_pg.py
    └── e2e/
        ├── conftest.py
        └── test_real_api.py
```

---

## 2. 文件与源码的映射规则

**路径推导**：把 `src/datacloud_analysis/` 替换为 `tests/unit/unit/`，文件名前加 `test_`。

| 源码文件 | 对应测试文件 |
|----------|-------------|
| `src/datacloud_analysis/agent.py` | `tests/unit/unit/test_agent.py` |
| `src/datacloud_analysis/bootstrap.py` | `tests/unit/unit/test_bootstrap.py` |
| `src/datacloud_analysis/session/pg_opengauss.py` | `tests/unit/unit/session/test_pg_opengauss.py` |
| `src/datacloud_analysis/workspace/paths.py` | `tests/unit/unit/workspace/test_paths.py` |
| `src/datacloud_analysis/tools/data.py` | `tests/unit/unit/tools/test_data.py` |

每个源码文件**必须**有对应的测试文件，`__init__.py` 除外（除非含实际逻辑）。

---

## 3. 本模块专属 Fixture

### conftest.py 各层 Fixture

| 文件 | 关键 Fixture | 说明 |
|------|-------------|------|
| `datacloud-analysis/conftest.py` | `workspace_paths` | 临时目录 + DATACLOUD_WORKSPACE_* env 隔离 |
| `datacloud-analysis/unit/conftest.py` | `StubSaver`, `mock_cursor`, `stub_saver` | OpenGaussSaver 单元测试桩 |
| `datacloud-analysis/integration/conftest.py` | `initialized_sdk` | 调用 `bootstrap.setup()` / `teardown()` |

### StubSaver — OpenGaussSaver 的最小父类桩

`OpenGaussSaver` 是 mixin，测试时用 `StubSaver` 提供父类接口，避免 `patch` 打洞：

```python
from contextlib import contextmanager
from unittest.mock import MagicMock
from datacloud_analysis.session.pg_opengauss import OpenGaussSaver

class StubSaver(OpenGaussSaver):
    """最小父类桩，仅提供 OpenGaussSaver 调用的父类方法。"""
    def __init__(self, mock_cur: MagicMock) -> None:
        self._cur = mock_cur

    @contextmanager
    def _cursor(self, *, pipeline: bool = False):  # type: ignore[override]
        yield self._cur

    def _load_checkpoint_tuple(self, value):  # type: ignore[override]
        return value  # 直通，方便断言原始 dict

    def _search_where(self, config, filter, before):  # type: ignore[override]
        return ("", [])

    def _dump_blobs(self, *args):  # type: ignore[override]
        return []

    def _dump_writes(self, *args):  # type: ignore[override]
        return []
```

---

## 4. 本模块特有的 Patch 路径

`get_checkpointer()` 在函数内部 `from psycopg import Connection`，patch 路径须写被调用模块：

```python
# ✅ 正确 — patch psycopg 模块级，因为 Connection 是在函数内部导入的
with patch("psycopg.Connection.connect", return_value=mock_conn):
    async with get_checkpointer() as cp:
        ...

# ❌ 错误 — 函数内部导入的名字不存在于模块作用域
with patch("datacloud_analysis.session.pg_opengauss.Connection.connect", ...):
    ...
```

---

## 5. 各模块覆盖率目标

运行命令（本模块专用）：

```bash
uv run pytest tests/unit/unit \
    --cov=datacloud_analysis \
    --cov-branch \
    --cov-report=term-missing
```

各源码模块的具体目标：

| 模块 | 目标覆盖率 | 说明 |
|------|-----------|------|
| `session/pg_opengauss.py` | ≥ 90% | 已有 40 个 unit 用例，重点补 fallback 分支 |
| `session/metadata.py` | ≥ 95% | 纯数据类，逻辑简单，应全量覆盖 |
| `workspace/paths.py` | ≥ 95% | 路径计算，无外部依赖 |
| `config/env.py` | ≥ 90% | 各字段默认值及必填校验需覆盖 |
| `agent.py` | ≥ 85% | LLM 调用需 mock，部分流程放 integration |
| `bootstrap.py` | ≥ 80% | 初始化链路复杂，部分放 integration |
| `tools/*.py` | ≥ 85% | 外部服务调用需 mock |
| `orchestration/*.py` | ≥ 85% | 调度逻辑，分支较多 |

---

## 6. 本模块禁止事项（补充根规范）

- **不得修改 `tests/datacloud_analysis/` 下的文件**（旧代码备份目录，只读）
