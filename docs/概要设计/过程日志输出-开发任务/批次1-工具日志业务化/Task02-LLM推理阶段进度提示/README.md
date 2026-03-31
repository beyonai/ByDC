# Task02 - LLM 推理阶段进度提示（think_text）

## 任务概述

在 `worker.py` 的 `_stream_graph` 方法中，监听 `on_chat_model_start` 事件，按当前所在图节点推送对应的 `think_text` 进度描述，填补 LLM 推理期间的静默空白。

---

## 背景

LLM 推理期间（`on_chat_model_start` → `on_chat_model_end`）可能持续数秒，期间前端无任何输出，用户体验差。需要在每次 LLM 开始推理时，推送一条简短的业务描述告知用户当前在做什么。

---

## 开发内容

### 1. 新增常量：`_NODE_THINKING_DESC`

文件：`datacloud_service/worker.py`（模块顶层）

```python
_NODE_THINKING_DESC: dict[str, str] = {
    "knowledge_enhance": "正在理解业务术语...",
    "planning":          "正在分解分析任务...",
    "execution":         "正在决策执行步骤...",
    "end":               "正在生成分析结论...",
}
```

### 2. 在 `_stream_graph` 的事件循环中新增分支

在 `astream_events` 循环的事件处理中，新增 `on_chat_model_start` 分支：

```python
elif kind == "on_chat_model_start":
    node_name = event.get("metadata", {}).get("langgraph_node", "")
    desc = _NODE_THINKING_DESC.get(node_name, "正在深入分析，请稍候...")
    await context.emit_chunk(
        StreamChunkEvent(content=desc),
        event_type=EventType.REASONING_LOG_START.value,
        content_type=SseReasonMessageType.think_text.value,
    )
```

> 注意：`on_chat_model_stream` 事件（token 流）由 `insight_node` 内部自行推送，`worker.py` 中不处理该事件，避免重复转发。

---

## 涉及文件

| 文件 | 改动类型 |
|------|---------|
| `examples/e_commerce_demo/backend/datacloud_service/worker.py` | 新增常量、新增事件处理分支 |

---

## 验收标准

1. 发起一次数据查询，在 LLM 开始推理时（`on_chat_model_start`），前端过程日志中出现对应描述：
   - `knowledge_enhance` 节点 → "正在理解业务术语..."
   - `planning` 节点 → "正在分解分析任务..."
   - `execution` 节点 → "正在决策执行步骤..."
   - `end` 节点 → "正在生成分析结论..."
2. 未命中节点名时，显示兜底描述"正在深入分析，请稍候..."。
3. `think_text` 消息出现在折叠区块内，不影响最终答案区域。
4. 原有功能不受影响，最终答案内容不变。
