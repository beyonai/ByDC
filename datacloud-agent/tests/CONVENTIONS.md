# 测试用例文件建立规范

> 适用范围：`datacloud-agent` 项目，测试目录 `tests/`

---

## 1. 目录结构总览

```
tests/
├── CONVENTIONS.md                   ← 本文件（规范说明）
├── datacloud_agent/                 ← 备份目录（旧代码，待废弃，勿新增）
└── datacloud-agent/                 ← 活跃测试目录（与 src/datacloud-agent/ 对应）
    ├── conftest.py                  ← 包级公共 fixture
    ├── unit/                        ← 单元测试（全 Mock，无真实 I/O）
    │   ├── conftest.py              ← unit 专属 fixture
    │   ├── test_agent.py            ← src/datacloud-agent/agent.py
    │   ├── config/
    │   │   └── test_env.py          ← src/datacloud-agent/config/env.py
    │   ├── gateway/
    │   │   ├── test_handler.py
    │   │   └── test_task_adapter.py
    │   ├── memory/
    │   │   ├── test_loader.py
    │   │   └── test_tools.py
    │   ├── orchestration/
    │   │   ├── test_dag.py
    │   │   ├── test_intent.py
    │   │   └── test_loop.py
    │   ├── session/
    │   │   ├── test_checkpointer.py ← src/datacloud-agent/session/checkpointer.py
    │   │   ├── test_metadata.py     ← src/datacloud-agent/session/metadata.py
    │   │   └── test_pg_opengauss.py ← src/datacloud-agent/session/pg_opengauss.py
    │   ├── skills/
    │   │   └── test_builtin.py
    │   └── workspace/
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
| `src/datacloud-agent/session/pg_opengauss.py` | `tests/datacloud-agent/unit/session/test_pg_opengauss.py` |
| `src/datacloud-agent/workspace/paths.py` | `tests/datacloud-agent/unit/workspace/test_paths.py` |

**路径推导方式**：把 `src/datacloud-agent/` 替换为 `tests/datacloud-agent/unit/`，在文件名前加 `test_`。

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

---

## 4. 测试类型划分标准

| 类型 | 目录 | 判断标准 | 典型运行时间 |
|------|------|----------|-------------|
| **unit** | `unit/` | 全 Mock，无真实 I/O，无网络，无 DB | < 100ms / 用例 |
| **integration** | `integration/` | 需要真实 DB（psycopg 连接、bootstrap） | 秒级 |
| **e2e** | `e2e/` | 完整业务流程，跨多个服务 | 分钟级 |

集成测试必须加 marker：

```python
@pytest.mark.integration
async def test_bootstrap_creates_pg_tables(): ...
```

---

## 5. conftest.py 分层原则

| 文件 | 放置内容 |
|------|----------|
| `datacloud-agent/conftest.py` | 整个包通用的 fixture（如 `workspace_paths`）|
| `datacloud-agent/unit/conftest.py` | unit 专属：mock LLM、mock checkpointer、stub DB |
| `datacloud-agent/integration/conftest.py` | `initialized_sdk`（需要真实 PG 环境）|

**原则**：Fixture 只在需要它的最窄范围定义，避免 fixture 泄漏到不需要它的测试。

---

## 6. Mock 策略

### 单元测试：隔离所有外部依赖

```python
# ✅ 正确：Mock DB 连接，只测逻辑
def test_get_tuple_returns_none_when_no_row():
    saver = _make_stub_saver(fetchone_return=None)
    result = saver.get_tuple({"configurable": {"thread_id": "t1", "checkpoint_ns": ""}})
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

---

## 7. 异步测试

项目使用 `pytest-asyncio`，`asyncio_mode = "auto"`，直接用 `async def` 即可：

```python
async def test_aget_tuple_delegates_to_sync_inner():
    inner = MagicMock()
    inner.get_tuple.return_value = "sentinel"
    wrapper = SyncPGCheckpointer(inner)
    result = await wrapper.aget_tuple({"configurable": {"thread_id": "t1"}})
    assert result == "sentinel"
```

---

## 8. 禁止事项

- 单元测试不得建立真实网络连接或 DB 连接
- 不得在测试方法里写 `time.sleep()`
- 不得在 `unit/` 下使用 `@pytest.mark.integration`
- 不得跨测试文件做相对 import（使用 fixture 传递共享对象）
- 不得修改 `tests/datacloud_agent/` 下的文件（备份目录，只读）
