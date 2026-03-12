# 测试用例文件建立规范

> 适用范围：`datacloud-agent` 项目，测试目录 `tests/`
>
> **覆盖率目标：单元测试行覆盖率 ≥ 90%，分支覆盖率 ≥ 85%**

---

## 目录

1. [目录结构总览](#1-目录结构总览)
2. [文件与源码的映射规则](#2-文件与源码的映射规则)
3. [文件内部命名规范](#3-文件内部命名规范)
4. [测试类型划分标准](#4-测试类型划分标准)
5. [conftest.py 分层原则](#5-conftestpy-分层原则)
6. [Mock 策略](#6-mock-策略)
7. [异步测试](#7-异步测试)
8. [覆盖率标准与度量](#8-覆盖率标准与度量)
9. [达成 90% 覆盖率的方法论](#9-达成-90-覆盖率的方法论)
10. [禁止事项](#10-禁止事项)

---

## 1. 目录结构总览

```
tests/
├── CONVENTIONS.md                   ← 本文件（规范说明）
├── datacloud_agent/                 ← 备份目录（旧代码，待废弃，勿新增）
└── datacloud-agent/                 ← 活跃测试目录（与 src/datacloud-agent/ 对应）
    ├── conftest.py                  ← 包级公共 fixture
    ├── unit/                        ← 单元测试（全 Mock，无真实 I/O）
    │   ├── conftest.py              ← unit 专属 fixture（StubSaver、mock_cursor…）
    │   ├── test_agent.py            ← src/datacloud-agent/agent.py
    │   ├── test_bootstrap.py        ← src/datacloud-agent/bootstrap.py
    │   ├── config/
    │   │   ├── test_env.py          ← src/datacloud-agent/config/env.py
    │   │   └── test_models.py       ← src/datacloud-agent/config/models.py
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
    │   │   ├── test_checkpointer.py ← src/datacloud-agent/session/checkpointer.py
    │   │   ├── test_metadata.py     ← src/datacloud-agent/session/metadata.py
    │   │   └── test_pg_opengauss.py ← src/datacloud-agent/session/pg_opengauss.py
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
    ├── integration/                 ← 集成测试（需要真实 DB / 服务）
    │   ├── conftest.py              ← initialized_sdk fixture
    │   └── test_bootstrap_pg.py
    └── e2e/                         ← 端到端测试（完整业务链路）
        ├── conftest.py
        └── test_real_api.py
```

---

## 2. 文件与源码的映射规则

### 规则：一文件对一模块

| 源码文件 | 对应测试文件 |
|----------|-------------|
| `src/datacloud-agent/agent.py` | `tests/datacloud-agent/unit/test_agent.py` |
| `src/datacloud-agent/bootstrap.py` | `tests/datacloud-agent/unit/test_bootstrap.py` |
| `src/datacloud-agent/session/pg_opengauss.py` | `tests/datacloud-agent/unit/session/test_pg_opengauss.py` |
| `src/datacloud-agent/workspace/paths.py` | `tests/datacloud-agent/unit/workspace/test_paths.py` |
| `src/datacloud-agent/tools/data.py` | `tests/datacloud-agent/unit/tools/test_data.py` |

**路径推导方式**：把 `src/datacloud-agent/` 替换为 `tests/datacloud-agent/unit/`，在文件名前加 `test_`。

### 覆盖范围要求

每个源码文件 **必须** 有对应的测试文件，`__init__.py` 除外（除非 `__init__.py` 包含实际逻辑）。

---

## 3. 文件内部命名规范

### 测试类命名：对应源码类

```python
# 源码：class OpenGaussSaver
class TestOpenGaussSaver:
    ...

# 源码：class SyncPGCheckpointer
class TestSyncPGCheckpointer:
    ...
```

### 测试方法命名：`test_<被测方法>_<场景描述>`

```python
class TestOpenGaussSaver:
    def test_fetch_blobs_returns_none_when_channel_versions_empty(self): ...
    def test_fetch_blobs_filters_by_version_in_python(self): ...
    def test_put_updates_on_duplicate_checkpoint(self): ...
```

**独立函数**（无对应类的源码）：`test_<函数名>_<场景描述>`

```python
def test_ensure_tables_opengauss_creates_all_tables(): ...
def test_get_checkpointer_raises_when_uri_missing(): ...
```

### 场景命名约定

| 场景类型 | 命名后缀示例 |
|----------|-------------|
| 正常路径 | `_returns_result`, `_creates_table`, `_delegates_to_inner` |
| 空/None 输入 | `_when_empty`, `_when_none`, `_when_not_found` |
| 异常/错误处理 | `_raises_on_missing_uri`, `_ignores_unique_violation` |
| 边界条件 | `_with_limit`, `_when_already_exists`, `_on_conflict` |

---

## 4. 测试类型划分标准

| 类型 | 目录 | 判断标准 | 典型运行时间 |
|------|------|----------|-------------|
| **unit** | `unit/` | 全 Mock，无真实 I/O，无网络，无 DB | < 100ms / 用例 |
| **integration** | `integration/` | 需要真实 DB（psycopg 连接、bootstrap） | 秒级 |
| **e2e** | `e2e/` | 完整业务流程，跨多个服务 | 分钟级 |

集成 / e2e 测试必须加 marker：

```python
@pytest.mark.integration
async def test_bootstrap_creates_pg_tables(): ...

@pytest.mark.e2e
async def test_full_analysis_pipeline(): ...
```

---

## 5. conftest.py 分层原则

| 文件 | 放置内容 |
|------|----------|
| `datacloud-agent/conftest.py` | 整个包通用的 fixture（如 `workspace_paths`）|
| `datacloud-agent/unit/conftest.py` | unit 专属：`StubSaver`、`mock_cursor`、mock LLM |
| `datacloud-agent/integration/conftest.py` | `initialized_sdk`（需要真实 PG 环境）|

**原则**：Fixture 只在需要它的最窄范围定义，避免 fixture 泄漏到不需要它的测试。

---

## 6. Mock 策略

### 单元测试：隔离所有外部依赖

```python
# ✅ 正确：Mock DB 连接，只测逻辑
def test_get_tuple_returns_none_when_no_row(stub_saver, mock_cursor):
    mock_cursor.fetchone.return_value = None
    result = stub_saver.get_tuple({"configurable": {"thread_id": "t1", "checkpoint_ns": ""}})
    assert result is None

# ❌ 错误：单元测试里连接真实 DB
def test_get_tuple_returns_none_when_no_row():
    conn = psycopg.connect(REAL_URI)
    ...
```

### Stub 优于 Patch

对 `OpenGaussSaver` 这种依赖父类接口的 mixin，优先创建 `_StubSaver` 提供最小父类接口，而不是用 `patch` 打洞：

```python
from contextlib import contextmanager
from unittest.mock import MagicMock

class _StubSaver(OpenGaussSaver):
    """最小父类桩，仅提供 OpenGaussSaver 调用的父类方法。"""
    def __init__(self, mock_cur: MagicMock) -> None:
        self._cur = mock_cur

    @contextmanager
    def _cursor(self, *, pipeline: bool = False):
        yield self._cur

    def _load_checkpoint_tuple(self, value):
        return value

    def _search_where(self, config, filter, before):
        return ("", [])

    def _dump_blobs(self, *args):
        return []

    def _dump_writes(self, *args):
        return []
```

### 本地导入函数的 Patch 路径

函数内部 `from xxx import yyy` 的情况，patch 路径要写**被调用端**（`psycopg.Connection.connect`），而非导入端：

```python
# pg_opengauss.py 内部：
#   async def get_checkpointer():
#       from psycopg import Connection  ← 在函数内部导入
#       conn = Connection.connect(...)

# ✅ 正确：patch psycopg 模块级
with patch("psycopg.Connection.connect", return_value=mock_conn):
    ...

# ❌ 错误：patch 模块内不存在的名字
with patch("datacloud_agent.session.pg_opengauss.Connection.connect"):
    ...
```

---

## 7. 异步测试

项目使用 `pytest-asyncio`，`asyncio_mode = "auto"`，直接用 `async def` 即可：

```python
async def test_aget_tuple_delegates_to_sync_inner():
    inner = MagicMock()
    inner.serde = None
    inner.get_tuple.return_value = "sentinel"
    wrapper = SyncPGCheckpointer(inner)
    result = await wrapper.aget_tuple({"configurable": {"thread_id": "t1"}})
    assert result == "sentinel"
```

---

## 8. 覆盖率标准与度量

### 目标

| 指标 | 门槛 | 说明 |
|------|------|------|
| **行覆盖率（line）** | **≥ 90%** | 主要衡量指标，低于此值 CI 失败 |
| **分支覆盖率（branch）** | **≥ 85%** | 覆盖 if/else 的两个方向 |

### 运行命令

```bash
# 本地开发：快速查看哪些行未被覆盖
uv run pytest tests/datacloud-agent/unit \
    --cov=datacloud_agent \
    --cov-branch \
    --cov-report=term-missing

# 生成 HTML 报告（逐行高亮，强烈推荐用于补测）
uv run pytest tests/datacloud-agent/unit \
    --cov=datacloud_agent \
    --cov-branch \
    --cov-report=html:coverage_html
# 然后打开 coverage_html/index.html

# CI 门槛检查（低于 90% 则退出码非零）
uv run pytest tests/datacloud-agent/unit \
    --cov=datacloud_agent \
    --cov-branch \
    --cov-fail-under=90
```

### pyproject.toml 配置（已固化）

```toml
[tool.coverage.run]
source = ["src/datacloud-agent"]
branch = true                        # 开启分支覆盖
omit = [
    "*/tests/*",
    "*/__init__.py",
    "*/config/__init__.py",
]

[tool.coverage.report]
fail_under = 90                      # 低于 90% 报错
show_missing = true
skip_covered = false
exclude_lines = [
    # 以下模式不计入覆盖率
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "raise NotImplementedError",
    "@overload",
    "^\\.\\.\\.\\s*$",              # 只有省略号的行
]
```

### 理解覆盖率报告输出

```
Name                                       Stmts   Miss Branch BrPart  Cover   Missing
---------------------------------------------------------------------------------------
datacloud_agent/session/pg_opengauss.py     210     15     62      8    90%   105-120, 312
```

| 列 | 含义 |
|----|------|
| `Stmts` | 总可执行语句数 |
| `Miss` | 未被执行的语句数 |
| `Branch` | 总分支数（每个 if 有 2 个分支）|
| `BrPart` | 只走了一个方向的分支数 |
| `Cover` | 综合覆盖率 |
| `Missing` | 未覆盖的具体行号 → **补测的入手点** |

---

## 9. 达成 90% 覆盖率的方法论

### 第一步：识别未覆盖代码

```bash
# 生成 HTML 报告后，用浏览器查看红色高亮行
uv run pytest tests/datacloud-agent/unit \
    --cov=datacloud_agent --cov-branch --cov-report=html:coverage_html
```

HTML 报告里：
- **红色行** = 从未被执行（缺少对应测试）
- **橙色行** = 分支覆盖不完整（只走了 if 没走 else，或反之）

### 第二步：四类未覆盖场景及应对方式

#### ① 异常处理分支（`except` 块）

```python
# 源码：except UniqueViolation 分支
try:
    cur.execute(self._INS_CHK, ...)
except pge.UniqueViolation:
    cur.execute(self._UPD_CHK, ...)   # ← 橙色：未触发
```

**补测方式**：用 `side_effect` 让 mock 抛出异常：

```python
def test_put_updates_on_unique_violation(stub_saver, mock_cursor):
    import psycopg.errors
    mock_cursor.execute.side_effect = [
        psycopg.errors.UniqueViolation(),  # INSERT 失败
        None,                              # UPDATE 成功
    ]
    stub_saver.put(config, checkpoint, {}, {})
    sqls = [c[0][0] for c in mock_cursor.execute.call_args_list]
    assert any("UPDATE" in s for s in sqls)
```

#### ② 条件分支（`if/else`）

```python
# 源码：schema 存在时设置 search_path
if checkpoint_schema:          # ← 两个分支都需要测
    conn.execute(...)
```

**补测方式**：分别写有 schema 和无 schema 的测试：

```python
async def test_get_checkpointer_sets_search_path_when_schema_provided(monkeypatch):
    monkeypatch.setenv("DATACLOUD_PG_CHECKPOINT_URI", "postgresql://...")
    monkeypatch.setenv("DATACLOUD_PG_CHECKPOINT_SCHEMA", "myschema")
    ...
    mock_conn.execute.assert_called()  # 应调用 SET search_path

async def test_get_checkpointer_skips_schema_when_not_set(monkeypatch):
    monkeypatch.setenv("DATACLOUD_PG_CHECKPOINT_URI", "postgresql://...")
    monkeypatch.delenv("DATACLOUD_PG_CHECKPOINT_SCHEMA", raising=False)
    ...
    mock_conn.execute.assert_not_called()  # 不应调用 SET search_path
```

#### ③ 回退路径（`fallback` 逻辑）

```python
# 源码：setup() 失败时回退到自定义 DDL
try:
    saver.setup()
except (errors.SyntaxError, errors.UndefinedObject):
    await loop.run_in_executor(None, ensure_tables_opengauss, ...)  # ← 未覆盖
```

**补测方式**：让 `setup()` 抛出对应异常：

```python
async def test_get_checkpointer_falls_back_to_custom_ddl_on_syntax_error(monkeypatch):
    ...
    mock_saver.setup.side_effect = psycopg.errors.SyntaxError()
    with patch("datacloud_agent.session.pg_opengauss.ensure_tables_opengauss") as mock_ddl:
        async with get_checkpointer() as cp:
            pass
    mock_ddl.assert_called_once()
```

#### ④ 不可达代码（`pragma: no cover` 合法用法）

对于防御性断言、类型收窄等逻辑，确认确实无法在业务场景中触发后，可以用注释排除：

```python
else:
    raise AssertionError("should not reach here")  # pragma: no cover
```

**注意**：不得滥用 `pragma: no cover` 规避覆盖率，仅限上述场景。每次使用须在 code review 中说明理由。

### 第三步：分模块覆盖率目标

| 模块 | 目标覆盖率 | 说明 |
|------|-----------|------|
| `session/pg_opengauss.py` | ≥ 90% | 已有 40 个 unit 用例，补充 fallback 分支 |
| `session/metadata.py` | ≥ 95% | 纯数据类，逻辑简单，应全量覆盖 |
| `workspace/paths.py` | ≥ 95% | 路径计算，无外部依赖 |
| `config/env.py` | ≥ 90% | 环境变量解析，各字段默认值需覆盖 |
| `agent.py` | ≥ 85% | LLM 调用需 mock，部分流程放 integration |
| `bootstrap.py` | ≥ 80% | 初始化链路复杂，部分放 integration |
| `tools/*.py` | ≥ 85% | 外部服务调用需 mock |
| `orchestration/*.py` | ≥ 85% | 调度逻辑，分支较多 |

### 第四步：补测优先级排序

用以下原则决定补测顺序（高 → 低）：

1. **核心路径**：主流程（`get_tuple`, `put`, `create_agent`）的每个分支
2. **异常路径**：`except` 块、参数校验失败、资源不存在
3. **配置变化**：有 / 无某个环境变量的两种行为
4. **边界条件**：空列表、None 值、超长字符串等

---

## 10. 禁止事项

- 单元测试不得建立真实网络连接或 DB 连接
- 不得在测试方法里写 `time.sleep()`
- 不得在 `unit/` 下使用 `@pytest.mark.integration` 或 `@pytest.mark.e2e`
- 不得跨测试文件做相对 import（使用 fixture 传递共享对象）
- 不得修改 `tests/datacloud_agent/` 下的文件（备份目录，只读）
- 不得滥用 `# pragma: no cover`（每次使用须 code review 说明理由）
- 不得为了提高覆盖率数字而写无断言的"空转"测试（空测试反而掩盖问题）
