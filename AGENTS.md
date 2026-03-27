# AGENTS

**项目:** whale-datacloud
**Python:** >=3.12
**工具链:** uv + ruff + mypy

---

## Architecture

- Core SDKs are in `packages/`.
- Demo applications are in `examples/`.
- Project-level tests are in `tests/`.

## Principles

- Keep package boundaries clear.
- Prefer small, testable changes.
- Follow repository coding and testing conventions.

---

## 工具链 (2026)

| 用途 | 工具 | 命令 |
|------|------|------|
| 包管理 | `uv` | `uv sync`, `uv add` |
| 格式化 | `ruff format` | `uv run ruff format .` |
| Lint | `ruff check` | `uv run ruff check .` |
| 类型检查 | `mypy` | `uv run mypy .` |
| 测试 | `pytest` | `uv run pytest` |

## 规范

### Python 环境
- 使用 `uv` 管理 Python 版本和依赖
- Python >= 3.12

### 代码风格
- **Ruff** 格式化 + Lint
- 行宽 100，双引号，4 空格缩进
- 启用规则: E, F, I, N, W, UP, B, C4, SIM, ASYNC, S, DTZ, LOG, PTH, RET, TRY, TC 等

### 类型检查
- **MyPy strict mode**
- 必须带类型注解
- `# type: ignore` 必须带错误码

### Git Workflow

**Commit 格式（中文）：**
```
<type>(<scope>): <描述>

types: feat / fix / docs / style / refactor / test / chore
```

**Atomic Commits:**
- 一个 commit 一个逻辑变更
- 实现与测试一起提交

## Anti-Patterns

- ❌ `from ... import *` — 禁用通配符导入
- ❌ `# type: ignore` 不带错误码
- ❌ `as any` — 禁用类型抑制
- ❌ `eval()`, `exec()` — 禁用动态代码执行
- ❌ 裸 `except:` — 必须指定异常类型
- ❌ `print()` 生产代码 — 用 `logging`

## Commands

```bash
# 安装依赖
uv sync

# 格式化 + Lint
uv run ruff format .
uv run ruff check . --fix

# 类型检查
uv run mypy .

# 测试
uv run pytest
uv run pytest -m db_integration  # 数据库集成测试
```