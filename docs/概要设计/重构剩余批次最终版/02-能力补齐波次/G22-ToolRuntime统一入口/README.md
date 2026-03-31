# G22 ToolRuntime 统一入口

## 1. 任务定义

### 1.1 背景（§4.6）

重构方案 §4.6 要求：工具执行有统一入口 `ToolRuntime.invoke_with_callbacks`，负责：
1. 解析工具参数
2. 执行 before hook 链（patch/interrupt/fail）
3. 调用工具实现
4. 执行 after hook 链（recover/fail）
5. 返回标准化结果

**当前实现：** `execute_next_task()` 函数（`sandbox_executor.py`）承担了上述职责，但以函数式方式实现，hook 调用分散在函数内部，没有统一的 `ToolRuntime` 类封装。

**差距：**
- 无 `ToolRuntime` 类，无法通过依赖注入替换 hook 链
- `execute_next_task` 函数签名复杂（4 个参数），调用方需了解内部细节
- hook 上下文构建（`_build_hook_context`）与工具执行逻辑耦合

### 1.2 目标

将 `execute_next_task` 重构为 `ToolRuntime` 类，提供 `invoke_with_callbacks` 统一入口。

---

## 2. 详细任务

### 2.1 ToolRuntime 类设计

在 `execution/sandbox_executor.py`（G21 重组后路径）中新增 `ToolRuntime` 类：

```python
class ToolRuntime:
    """统一工具执行入口，封装 before/after hook 链。"""

    def __init__(
        self,
        custom_tools: dict[str, Any] | None = None,
        gateway_context: Any = None,
    ) -> None:
        self._custom_tools = custom_tools or {}
        self._gateway_context = gateway_context

    async def invoke_with_callbacks(
        self,
        task: dict[str, Any],
        state: Mapping[str, Any],
    ) -> tuple[dict[str, Any], Any]:
        """执行单个 todo 任务，统一走 before/after hook 链。

        Returns:
            (updated_task, output) — 与原 execute_next_task 返回值兼容。
        """
        ...
```

**实现要求：**
- 内部逻辑与现有 `execute_next_task` 等价，不改变行为
- 保留 `execute_next_task` 作为向后兼容的模块级函数（委托给 `ToolRuntime`）：
  ```python
  async def execute_next_task(task, state, gateway_context=None, custom_tools=None):
      """向后兼容入口，委托给 ToolRuntime.invoke_with_callbacks。"""
      rt = ToolRuntime(custom_tools=custom_tools, gateway_context=gateway_context)
      return await rt.invoke_with_callbacks(task, state)
  ```

### 2.2 execution/node.py 中的调用方式更新

`execution/node.py` 中创建 `ToolRuntime` 实例并复用：

```python
# 在 execution_node 或 _execute_one_todo 中
runtime = ToolRuntime(custom_tools=default_tools, gateway_context=gateway_context)
updated_task, output = await runtime.invoke_with_callbacks(active_todo, state)
```

### 2.3 单元测试

新增 `tests/dca/unit/test_tool_runtime.py`：

```python
"""ToolRuntime 统一入口测试。"""
import pytest
from unittest.mock import AsyncMock, patch

from datacloud_analysis.orchestration.execution.sandbox_executor import ToolRuntime


@pytest.mark.asyncio
async def test_tool_runtime_invoke_calls_before_after_hooks():
    """invoke_with_callbacks 必须依次调用 before 和 after hook。"""
    ...


@pytest.mark.asyncio
async def test_tool_runtime_before_interrupt_short_circuits():
    """before hook 返回 interrupt 时，工具不执行，直接返回中断结果。"""
    ...


@pytest.mark.asyncio
async def test_execute_next_task_compat_delegates_to_runtime():
    """execute_next_task 向后兼容函数委托给 ToolRuntime。"""
    ...
```

---

## 3. 验收标准

| # | 验收项 | 检查方式 |
|---|--------|---------|
| 1 | `ToolRuntime` 类存在于 `sandbox_executor.py` | `grep "class ToolRuntime" sandbox_executor.py` 有结果 |
| 2 | `invoke_with_callbacks` 方法存在 | `grep "invoke_with_callbacks" sandbox_executor.py` 有结果 |
| 3 | `execute_next_task` 向后兼容保留 | 现有调用方无需修改 |
| 4 | before hook interrupt 行为不变 | `test_tool_hook_plugin_manager.py` 持续绿色 |
| 5 | 新增单元测试通过 | `pytest tests/dca/unit/test_tool_runtime.py` 绿色 |
| 6 | 全量单测通过 | `pytest packages/datacloud-analysis/tests/` 绿色 |

---

## 4. 依赖

**前置**：01-收口前置波次完成（G21 目录重组后路径稳定）。

## 5. 并行性

可与 G23、G24、G25 并行执行。

## 6. 提交规范

```
refactor(g22): introduce ToolRuntime class with invoke_with_callbacks unified entry
```
