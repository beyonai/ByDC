# 编码规范（Coding Conventions）

> **适用范围**：`whale-datacloud` Monorepo 所有 Python 子项目
> （`datacloud-agent` / `datacloud-memory` / `datacloud-data-service` / `datacloud-knowledge-service` / `datacloud-mock`）
>
> **自动执行层**：根 `pyproject.toml` 已统一配置 Ruff（格式/Lint）和 MyPy（类型检查），本文档补充**工具无法检测的设计原则**。
>
> **子项目扩展**：各子项目在 `docs/CODING_CONVENTIONS.md` 中补充自身专项规范，并在文件头注明 `extends: /docs/CODING_CONVENTIONS.md`。

---

## 目录

1. [模块与文档规范](#1-模块与文档规范)
2. [环境变量规范](#2-环境变量规范)
3. [架构分层规则](#3-架构分层规则)
4. [类型注解规范](#4-类型注解规范)
5. [异步编程规范](#5-异步编程规范)
6. [错误处理规范](#6-错误处理规范)
7. [日志规范](#7-日志规范)
8. [相关文档](#8-相关文档)

---

## 1. 模块与文档规范

### 1.1 每个模块必须有 "Why" Docstring

文件头的模块 docstring 说明**为什么这个模块存在**，而非只重复文件名。

```python
# ✅ 正确 — 说明存在理由和边界约束
"""Business ID → LangGraph thread_id mapping (design §4.1.3.1).

This is the **only** module allowed to build LangGraph run configs.
Other modules must call build_run_config() instead of constructing
the dict themselves.
"""

# ❌ 错误 — 只是重复文件名
"""Session metadata module."""
```

### 1.2 类 Docstring 格式

```python
class SessionMetadata:
    """Immutable bundle of IDs for one Agent run.

    Attributes
    ----------
    thread_id:  LangGraph thread ID（由 Agent 自动生成）
    session_id: 来自调用方的业务会话 ID
    user_id:    触发任务的用户 ID
    """
```

### 1.3 函数 Docstring 格式（公开函数必须写）

```python
def build_task_paths(user_id: str, task_id: str) -> TaskPaths:
    """Construct the TaskPaths for a specific user+task.

    Args:
        user_id: The user who owns this task.
        task_id: The unique task identifier.

    Returns:
        A frozen TaskPaths with all paths fully resolved.

    Raises:
        pydantic.ValidationError: If workspace env vars are missing.
    """
```

### 1.4 注释原则：只写"为什么"，不写"是什么"

```python
# ✅ 正确 — 解释非显而易见的决策
# Lazy-create the lock inside the running event loop to avoid
# "no current event loop" error on Python 3.12+ with asyncio.Lock().
if _init_lock is None:
    _init_lock = asyncio.Lock()

# ❌ 错误 — 只是重复代码的含义
# Create lock
if _init_lock is None:
    _init_lock = asyncio.Lock()
```

### 1.5 每个 Python 文件头部

```python
"""<模块 Why docstring>."""

from __future__ import annotations
```

`from __future__ import annotations` 为**强制要求**（PEP 563 延迟注解求值）。

---

## 2. 环境变量规范

### 2.1 黄金规则：所有 env var 必须经过 Pydantic BaseSettings

```python
# ✅ 正确 — 通过 Settings 读取
from my_service.config.env import ServiceSettings
cfg = ServiceSettings()
url = cfg.base_url

# ❌ 禁止 — 直接调用 os.getenv
import os
url = os.getenv("MY_SERVICE_BASE_URL")
```

**唯一例外**：`config/env.py` 内部，以及读取框架约定变量（`OPENAI_API_KEY` 等）。

### 2.2 命名规范

```
<PROJECT>_<GROUP>_<KEY>

示例（datacloud-agent）：
  DATACLOUD_PG_CHECKPOINT_URI
  DATACLOUD_WORKSPACE_PUBLIC_ROOT
  DATACLOUD_LLM_REASONING_MODEL
```

### 2.3 新配置项的声明规范

```python
class PGSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATACLOUD_PG_", extra="ignore")

    checkpoint_uri: str = Field(
        ...,                     # 无 default = 必填，进程启动时即报错
        description="Full PostgreSQL DSN, e.g. postgresql://user:pass@host/db",
    )
    checkpoint_schema: str = Field(
        default="public",        # 可选项给合理默认值
        description="Schema for checkpoint tables.",
    )
```

---

## 3. 架构分层规则

### 3.1 每个子项目自行定义分层

各子项目在自己的 `docs/CODING_CONVENTIONS.md` 中声明：
- 内部模块的依赖方向
- "唯一读取点"约束（哪些模块有排他性职责）
- 不允许反向依赖的规则

### 3.2 局部导入（函数内 import）

重型依赖或避免循环依赖时，在函数体内 import，加 `# noqa: PLC0415` 和原因注释：

```python
async def get_checkpointer():
    from psycopg import Connection  # noqa: PLC0415  — 避免启动时即建立 DB 连接
    conn = Connection.connect(uri)
    ...
```

### 3.3 子项目间依赖规则

- 依赖关系通过 `pyproject.toml` 的 `[tool.uv.sources]` 声明
- 不得在代码里用路径 hack（`sys.path.insert`）导入兄弟项目
- 循环依赖（A 依赖 B，B 依赖 A）严格禁止

---

## 4. 类型注解规范

### 4.1 基本要求（MyPy strict 强制）

- 所有公开函数的参数和返回值必须有类型注解
- 裸 `Any` 仅用于框架边界代码（如覆写父类方法），须加注释

### 4.2 联合类型写法（Python 3.12+）

```python
# ✅
def foo(x: str | None) -> int | None: ...

# ❌ 旧式
from typing import Optional
def foo(x: Optional[str]) -> Optional[int]: ...
```

### 4.3 TYPE_CHECKING 守卫（避免运行时导入重型库）

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from psycopg_pool import AsyncConnectionPool
```

### 4.4 覆写父类方法

```python
@contextmanager
def _cursor(self, *, pipeline: bool = False):  # type: ignore[override]
    # OpenGauss-specific: yields mock cursor in tests
    yield self._cur
```

---

## 5. 异步编程规范

### 5.1 I/O 密集型操作必须用 async

```python
# ✅
async def fetch(url: str) -> dict:
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(url)
        return resp.json()

# ❌ — 在 async 上下文中用同步 HTTP，会阻塞 event loop
def fetch(url: str) -> dict:
    return requests.get(url).json()
```

### 5.2 阻塞同步代码用 run_in_executor

```python
# ✅ — 委托给线程池，不阻塞 event loop
async def aget_result(self, config: Any) -> Any:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, self._inner.get, config)

# ❌ — 直接调用同步阻塞函数
async def aget_result(self, config: Any) -> Any:
    return self._inner.get(config)  # 阻塞！
```

### 5.3 资源用 context manager 管理

```python
# ✅
async with httpx.AsyncClient() as client:
    await client.post(...)

# ❌ — 忘记关闭
client = httpx.AsyncClient()
await client.post(...)
```

### 5.4 对外暴露的异步资源工厂用 @asynccontextmanager

```python
@asynccontextmanager
async def get_resource() -> AsyncIterator[Resource]:
    resource = Resource.connect(...)
    try:
        yield resource
    finally:
        resource.close()   # 确保即使 body 抛异常也能释放
```

---

## 6. 错误处理规范

### 6.1 启动时 Fail-Fast

配置类错误（缺 env var、DB 不可达）在进程启动时立即报错：

```python
# ✅ — ValidationError 在进程启动的 setup() 阶段抛出
settings = Settings()

# ❌ — 运行时才发现缺配置
url = os.getenv("MY_URI") or ""
conn = connect(url)   # 空串时才报错，太晚了
```

### 6.2 异常必须有类型

```python
# ✅
except psycopg.errors.UniqueViolation:
    pass  # duplicate already stored; expected in upsert fallback

# ❌ — 裸 except 掩盖所有问题
except Exception:
    pass
```

### 6.3 BLE001（裸 except Exception）合法场景

仅限以下两种场景，且须加注释说明：

```python
# 1. 可选依赖软失败
try:
    from some_optional import feature
    feature()
except Exception:  # noqa: BLE001
    pass  # optional feature not available

# 2. model_validator 中逐个加载可选配置
try:
    object.__setattr__(self, attr, OptionalSettings.load())
except Exception:  # noqa: BLE001
    pass  # Role not configured; callers must check for None
```

### 6.4 RuntimeError 用于"开发者误用"

```python
def get_pool() -> Pool:
    if not _initialized:
        raise RuntimeError(
            "Service not initialized. "
            "Call `await setup()` at process startup before using this function."
        )
    return _pool
```

---

## 7. 日志规范

### 7.1 每个模块独立 logger

```python
import logging
logger = logging.getLogger(__name__)   # ✅

# ❌
print("model:", model)                 # 禁止 print
logging.info("model: %s", model)       # 禁止使用 root logger
```

### 7.2 日志级别标准

| 级别 | 用途 |
|------|------|
| `DEBUG` | 开发调试，函数入参、中间状态 |
| `INFO` | 生命周期事件（"pool opened", "setup complete"）|
| `WARNING` | 降级运行（"locale not supported, falling back"）|
| `ERROR` | 需要人工介入（连接失败、数据损坏）|

### 7.3 格式要求

```python
# ✅ — %s 格式（lazy evaluation）
logger.info("request: method=%s url=%s", method, url)

# ❌ — f-string 在任何级别都会提前求值
logger.info(f"request: {method} {url}")
```

### 7.4 日志禁止包含

- 密码、API Key、数据库连接串（只记录 host:port）
- 用户输入的完整原文（可截断至 100 字）

---

## 8. 相关文档

| 文档 | 说明 |
|------|------|
| 本文档 | 全项目通用编码规范 |
| [`docs/TESTING_CONVENTIONS.md`](./TESTING_CONVENTIONS.md) | 全项目通用测试规范 |
| [`datacloud-agent/docs/CODING_CONVENTIONS.md`](../datacloud-agent/docs/CODING_CONVENTIONS.md) | datacloud-agent 专项规范（扩展本文档）|
| [`datacloud-agent/tests/CONVENTIONS.md`](../datacloud-agent/tests/CONVENTIONS.md) | datacloud-agent 测试专项规范（扩展本文档）|

---

## 附录：工具自动化范围

| 规范项 | 工具 | 命令 |
|--------|------|------|
| 代码格式 | Ruff format | `uv run ruff format .` |
| Lint 检查 | Ruff lint | `uv run ruff check .` |
| 类型安全 | MyPy strict | `uv run mypy .` |
| 测试覆盖率 ≥ 90% | pytest-cov | `uv run pytest --cov` |
| **本文档涵盖** | Code Review | 工具无法检测的设计原则 |
