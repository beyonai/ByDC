# Task01 - 工具映射常量与参数提取函数

## 任务概述

在 `worker.py` 中新增工具名业务化映射常量和参数提取函数，替换现有 `on_tool_start/end` 事件处理中输出原始工具名的逻辑，使前端展示对业务用户可读的描述。

---

## 背景

当前 `_stream_graph` 方法在处理 `on_tool_start` / `on_tool_end` 事件时，直接将内部工具名（如 `sbx_run_code`、`search_knowledge`）输出给前端，业务用户无法理解。

---

## 开发内容

### 1. 新增常量：`_TOOL_DISPLAY`

文件：`datacloud_service/worker.py`（模块顶层，与其他常量放在一起）

```python
_TOOL_DISPLAY: dict[str, tuple[str, str]] = {
    # 知识与记忆
    "search_knowledge":  ("正在查阅业务知识库", "业务知识查阅完成"),
    "recall_memory":     ("正在回忆相关经验",   "相关经验回忆完成"),
    # 代码执行
    "sbx_run_code":      ("正在执行数据分析",   "数据分析执行完成"),
    # 文件操作
    "sbx_read_file":     ("正在读取分析文件",   "分析文件读取完成"),
    "sbx_write_file":    ("正在保存分析结果",   "分析结果保存完成"),
    # 技能与报告
    "build_skill":       ("正在构建分析技能",   "分析技能构建完成"),
    "render_report":     ("正在生成分析报告",   "分析报告生成完成"),
    # ReAct 能力选择（execution 节点高频触发，无完成描述）
    "choose_capability": ("正在决策下一步操作", ""),
}
```

### 2. 新增函数：`_tool_display()`

```python
def _tool_display(tool_name: str) -> tuple[str, str]:
    """返回 (开始描述, 完成描述)，未命中时返回通用描述。"""
    return _TOOL_DISPLAY.get(tool_name, ("正在处理中...", "处理完成"))
```

### 3. 新增函数：`_extract_tool_detail()`

```python
import os

def _extract_tool_detail(tool_name: str, tool_input: Any) -> str:
    """从工具调用参数中提取对用户有意义的关键信息。"""
    if not isinstance(tool_input, dict):
        return ""
    if tool_name in ("sbx_read_file", "sbx_write_file"):
        path = tool_input.get("file_path") or tool_input.get("path", "")
        if path:
            return os.path.basename(str(path))  # 只取文件名，不暴露完整路径
    if tool_name in ("search_knowledge", "recall_memory"):
        query = tool_input.get("query", "")
        return str(query)[:30] if query else ""
    return ""
```

### 4. 修改 `_stream_graph` 中的事件处理

找到现有的 `on_tool_start` / `on_tool_end` 处理分支，替换为：

```python
elif kind == "on_tool_start":
    tool_name = event.get("name", "")
    tool_input = event.get("data", {}).get("input", {})
    start_desc, _ = _tool_display(tool_name)
    detail = _extract_tool_detail(tool_name, tool_input)
    display_text = f"{start_desc}：{detail}" if detail else start_desc
    await context.emit_chunk(
        StreamChunkEvent(content=display_text),
        event_type=EventType.TASK_CREATE.value,
        content_type=SseReasonMessageType.task_title.value,
    )

elif kind == "on_tool_end":
    tool_name = event.get("name", "")
    _, end_desc = _tool_display(tool_name)
    if end_desc:
        await context.emit_chunk(
            StreamChunkEvent(content=end_desc),
            event_type=EventType.STEP_COMPLETE.value,
            content_type=SseReasonMessageType.task_finished.value,
        )
```

---

## 涉及文件

| 文件 | 改动类型 |
|------|---------|
| `examples/e_commerce_demo/backend/datacloud_service/worker.py` | 新增常量、新增函数、修改事件处理分支 |

---

## 验收标准

1. 发起一次数据查询，前端过程日志中 **不再出现** `sbx_run_code`、`search_knowledge` 等原始工具名。
2. 调用 `sbx_read_file` / `sbx_write_file` 时，日志中显示文件名（如"正在读取分析文件：result.csv"），不显示完整路径。
3. 调用 `search_knowledge` 时，日志中显示查询关键词前30字（如"正在查阅业务知识库：品类 销售额"）。
4. `choose_capability` 工具触发时，只显示开始描述，无完成描述。
5. 未在映射表中的工具，显示"正在处理中..." / "处理完成"兜底描述。
6. 原有功能不受影响，最终答案内容不变。
