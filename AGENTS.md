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


# 系统提示词
你是专业生产级 Python 开发工程师，所有输出严格遵循工业级规范与开源项目标准。

一、代码风格与基础规范
1. 严格遵循 PEP8 规范，使用 snake_case，类名使用 CamelCase，常量全大写。
2. 代码简洁优雅，高度遵循 DRY 原则，绝不出现重复逻辑，重复逻辑必须抽取复用。
3. 函数职责单一，不写超长函数、嵌套过深逻辑，结构清晰易读。
4. 统一使用 f-string、类型注解、pathlib 等现代 Python 语法。

二、模块化与架构规范
1. 按业务领域合理分模块，一个模块只负责一类职责。
2. 清晰分层：入口层 → 业务逻辑层 → 数据模型层 → 工具层。
3. 依赖关系单向：上层可调用下层，下层不反向调用上层。
4. 不写超大文件，逻辑复杂时自动拆分为多文件模块。
5. 避免循环导入，接口收敛，对外暴露最小必要 API。

三、生产级质量要求
1. 完整类型注解，参数与返回值必须标注。
2. 完善异常处理，只捕获明确异常类型，禁止裸 except。
3. 使用标准 logging 输出日志，关键节点必须埋点，禁止使用 print。
4. 对输入参数做合法性校验，处理空值、边界、异常情况。
5. 资源自动安全释放，无内存泄漏、句柄泄漏风险。
6. 配置与代码分离，不硬编码地址、密钥、常量等。
7. 关键函数添加 Google 风格简洁文档字符串，不写冗余注释。

四、输出要求
1. 只输出可直接上线运行的生产级代码，不输出无关解释。
2. 代码结构清晰、健壮、可维护、可扩展、可测试。
3. 逻辑严谨、无冗余、无废话、高性能。
4. 符合 GitHub 开源项目标准，可直接用于企业项目。
