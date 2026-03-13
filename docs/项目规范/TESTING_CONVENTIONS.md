# 测试规范（Testing Conventions）

> **适用范围**：`whale-datacloud` Monorepo 所有 Python 子项目
>
> **覆盖率目标：单元测试行覆盖率 ≥ 90%，分支覆盖率 ≥ 85%**
>
> **子项目扩展**：各子项目在 `tests/CONVENTIONS.md` 中补充具体的目录结构和文件映射规则，并在文件头注明 `extends: /docs/TESTING_CONVENTIONS.md`。

---

## 目录

1. [测试目录结构约定](#1-测试目录结构约定)
2. [文件命名规范](#2-文件命名规范)
3. [测试类型划分标准](#3-测试类型划分标准)
4. [conftest.py 分层原则](#4-conftestpy-分层原则)
5. [Mock 策略](#5-mock-策略)
6. [异步测试](#6-异步测试)
7. [覆盖率标准与度量](#7-覆盖率标准与度量)
8. [达成 90% 覆盖率的方法论](#8-达成-90-覆盖率的方法论)
9. [禁止事项](#9-禁止事项)

---

## 1. 测试目录结构约定

每个子项目的测试目录遵循以下三层结构：

```
<subproject>/tests/
├── CONVENTIONS.md        ← 子项目测试规范（extends 本文档）
├── conftest.py           ← 项目级公共 fixture
├── unit/                 ← 单元测试（全 Mock，无真实 I/O）
│   └── conftest.py       ← unit 专属 fixture
├── integration/          ← 集成测试（需要真实 DB / 服务）
│   └── conftest.py
└── e2e/                  ← 端到端测试（完整业务链路）
    └── conftest.py
```

各子项目的 `tests/CONVENTIONS.md` 应补充：
- 测试文件与源码文件的具体映射规则
- `unit/` 下的子目录结构（按源码模块镜像）

---

## 2. 文件命名规范

### 测试文件：`test_<源码模块名>.py`

| 源码文件 | 对应测试文件 |
|----------|-------------|
| `src/my_service/parser.py` | `tests/unit/test_parser.py` |
| `src/my_service/db/client.py` | `tests/unit/db/test_client.py` |

**路径推导**：把 `src/<package>/` 替换为 `tests/unit/`，文件名前加 `test_`。

### 测试类：`Test<源码类名>`

```python
# 源码：class QueryEngine
class TestQueryEngine:
    ...
```

### 测试方法：`test_<被测方法>_<场景描述>`

```python
class TestQueryEngine:
    def test_execute_returns_results_when_query_is_valid(self): ...
    def test_execute_raises_on_empty_query(self): ...
    def test_execute_returns_empty_list_when_no_data(self): ...
```

### 场景命名约定

| 场景 | 后缀示例 |
|------|----------|
| 正常路径 | `_returns_result`, `_creates_record`, `_delegates_to_inner` |
| 空/None 输入 | `_when_empty`, `_when_none`, `_when_not_found` |
| 异常处理 | `_raises_on_missing_config`, `_ignores_duplicate` |
| 边界条件 | `_with_limit`, `_when_already_exists` |

---

## 3. 测试类型划分标准

| 类型 | 目录 | 判断标准 | 典型运行时间 |
|------|------|----------|-------------|
| **unit** | `unit/` | 全 Mock，无真实 I/O，无网络，无 DB | < 100ms / 用例 |
| **integration** | `integration/` | 需要真实 DB / 外部服务 | 秒级 |
| **e2e** | `e2e/` | 跨多个服务的完整链路 | 分钟级 |

集成 / e2e 测试必须加 marker：

```python
@pytest.mark.integration
async def test_bootstrap_creates_tables(): ...

@pytest.mark.e2e
async def test_full_pipeline(): ...
```

默认只跑 unit：

```bash
pytest -m "not integration and not e2e"
```

---

## 4. conftest.py 分层原则

| 文件 | 放置内容 |
|------|----------|
| `tests/conftest.py` | 整个子项目公共 fixture（如 tmp_path 包装）|
| `tests/unit/conftest.py` | unit 专属：mock 外部依赖、stub 数据库 |
| `tests/integration/conftest.py` | 需要真实连接的 fixture（如 `initialized_service`）|

**原则**：Fixture 定义在**需要它的最窄范围**，避免 unit/conftest.py 里出现真实 DB 连接。

---

## 5. Mock 策略

### 单元测试：完全隔离外部依赖

```python
# ✅ 正确 — Mock HTTP 客户端，只测业务逻辑
async def test_query_returns_data(mocker):
    mocker.patch("httpx.AsyncClient.post", return_value=mock_response({"rows": []}))
    result = await query_service.execute("show all deals")
    assert result == {"rows": []}

# ❌ 错误 — 单元测试连接真实服务
async def test_query_returns_data():
    result = await query_service.execute("show all deals")  # 会真正发 HTTP
```

### Stub 优于 Patch（用于 mixin / 抽象类）

对依赖父类接口的类，创建最小 Stub 而非 patch 打洞：

```python
class _StubClient(MyMixin):
    """仅提供 MyMixin 调用的父类方法。"""
    def _execute(self, sql: str) -> list:
        return self._mock_result

    def _cursor(self):
        return MagicMock()
```

### 本地导入函数的 patch 路径

函数内 `from xxx import yyy`，patch 路径要写**被调用模块**：

```python
# 函数内：from psycopg import Connection
# ✅ 正确
with patch("psycopg.Connection.connect", return_value=mock_conn):
    ...
# ❌ 错误（函数内导入的名字不在模块作用域）
with patch("my_module.Connection.connect", ...):
    ...
```

---

## 6. 异步测试

`asyncio_mode = "auto"`（已在根 `pyproject.toml` 配置），直接用 `async def`：

```python
async def test_aget_returns_result():
    inner = MagicMock()
    inner.serde = None
    inner.get.return_value = {"id": "c1"}
    wrapper = AsyncWrapper(inner)
    result = await wrapper.aget(config)
    assert result == {"id": "c1"}
```

---

## 7. 覆盖率标准与度量

### 目标

| 指标 | 门槛 |
|------|------|
| **行覆盖率（line）** | **≥ 90%** |
| **分支覆盖率（branch）** | **≥ 85%** |

### 运行命令

```bash
# 本地查看（显示未覆盖行号）
uv run pytest tests/unit \
    --cov=<package_name> \
    --cov-branch \
    --cov-report=term-missing

# HTML 报告（逐行查看哪些行未覆盖）
uv run pytest tests/unit \
    --cov=<package_name> \
    --cov-branch \
    --cov-report=html:coverage_html

# CI 门槛（低于 90% 失败）
uv run pytest tests/unit \
    --cov=<package_name> \
    --cov-branch \
    --cov-fail-under=90
```

### 根 pyproject.toml 统一配置

```toml
[tool.coverage.run]
branch = true
omit = ["*/tests/*", "*/__init__.py"]

[tool.coverage.report]
fail_under = 90
show_missing = true
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "raise NotImplementedError",
    "@overload",
    "^\\s*\\.\\.\\.\\s*$",
]
```

---

## 8. 达成 90% 覆盖率的方法论

### 第一步：生成 HTML 报告找缺口

```bash
uv run pytest tests/unit --cov=<pkg> --cov-branch --cov-report=html:coverage_html
```

- **红色行** = 从未被执行，需要补测试
- **橙色行** = 分支不完整（只走了 if 没走 else）

### 第二步：四类未覆盖场景的补测方式

| 场景 | 补测方式 |
|------|----------|
| `except` 块 | `side_effect` 让 mock 抛出对应异常 |
| `if/else` 两个方向 | 分别写两个测试用例 |
| fallback 路径 | mock 主路径失败，验证走了 fallback |
| 防御性断言 | 加 `# pragma: no cover` 并在 review 中说明 |

**示例：覆盖 except 分支**

```python
def test_put_updates_on_unique_violation(stub_saver, mock_cursor):
    import psycopg.errors
    mock_cursor.execute.side_effect = [
        psycopg.errors.UniqueViolation(),  # INSERT 触发冲突
        None,                              # UPDATE 成功
    ]
    stub_saver.put(config, checkpoint, {}, {})
    sqls = [c[0][0] for c in mock_cursor.execute.call_args_list]
    assert any("UPDATE" in s for s in sqls)
```

### 第三步：`pragma: no cover` 的合法使用

```python
# 合法：防御性断言，业务上不应到达
else:
    raise AssertionError("unreachable")  # pragma: no cover
```

**不得**滥用 `pragma: no cover` 规避覆盖率数字。每次使用须在 code review 中说明理由。

---

## 9. 禁止事项

- 单元测试不得建立真实网络连接或 DB 连接
- 不得在测试方法里写 `time.sleep()`
- 不得在 `unit/` 下使用 `@pytest.mark.integration` 或 `@pytest.mark.e2e`
- 不得为了提高覆盖率数字而写无断言的"空转"测试
- 不得滥用 `# pragma: no cover`（每次使用须 code review 说明）
- 不得跨测试文件做相对 import（用 fixture 传递共享对象）
