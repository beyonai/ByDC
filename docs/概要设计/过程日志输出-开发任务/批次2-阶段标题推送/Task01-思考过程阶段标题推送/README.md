# Task01 - 思考过程阶段标题推送（think_title）

## 任务概述

在 `worker.py` 的 `_stream_graph` 方法中，监听图节点的启动和 LLM 调用完成事件，按阶段推送 `think_title`，将整个处理过程划分为"问题理解 → 任务生成 → 任务执行 → 结果生成"四个阶段，在前端以折叠区块标题形式展示。

---

## 背景

当前过程日志只有一个固定标题"思考中..."，用户无法感知处理进展到哪个阶段。需要按图节点的实际执行阶段动态切换标题。

---

## 阶段划分与触发规则

| 阶段 title | 触发事件 | 触发条件 |
|-----------|---------|---------|
| 问题理解 | `on_chain_start` | `event["name"] == "knowledge_enhance"` |
| 任务生成 | `on_chat_model_end` | `event["metadata"]["langgraph_node"] == "planning"` |
| 任务执行 | `on_chain_start` | `event["name"] == "execution"`，仅首次 |
| 结果生成 | `on_chain_start` | `event["name"] == "end"` |

> 说明：
> - "问题理解"在 `knowledge_enhance` 启动时推送，覆盖知识库查询 + planning 前半段（意图解析）。
> - "任务生成"在 `planning` 的 LLM 调用结束后推送，此时任务列表已生成，标题切换有实际意义。
> - "任务执行"的 `execution` 节点会循环多次，通过去重集合只在首次进入时推送。

---

## 开发内容

### 1. 新增常量：`_NODE_PHASE_TITLE`

文件：`datacloud_service/worker.py`（模块顶层）

```python
_NODE_PHASE_TITLE: dict[str, str] = {
    "knowledge_enhance": "问题理解",
    # "planning" 的标题由 on_chat_model_end 触发，不在此映射
    "execution":         "任务执行",
    "end":               "结果生成",
}
```

### 2. 在 `_stream_graph` 方法开头初始化去重集合

```python
_phase_emitted: set[str] = set()
```

### 3. 在事件循环中新增两个处理分支

```python
# ── 阶段标题：问题理解 / 任务执行 / 结果生成 ──
elif kind == "on_chain_start":
    node_name = event.get("name", "")
    phase = _NODE_PHASE_TITLE.get(node_name)
    if phase and phase not in _phase_emitted:
        _phase_emitted.add(phase)
        await context.emit_chunk(
            StreamChunkEvent(content=phase),
            event_type=EventType.REASONING_LOG_START.value,
            content_type=SseReasonMessageType.think_title.value,
        )

# ── 阶段标题：任务生成（planning LLM 调用结束后） ──
elif kind == "on_chat_model_end":
    node_name = event.get("metadata", {}).get("langgraph_node", "")
    if node_name == "planning" and "任务生成" not in _phase_emitted:
        _phase_emitted.add("任务生成")
        await context.emit_chunk(
            StreamChunkEvent(content="任务生成"),
            event_type=EventType.REASONING_LOG_START.value,
            content_type=SseReasonMessageType.think_title.value,
        )
```

---

## 涉及文件

| 文件 | 改动类型 |
|------|---------|
| `examples/e_commerce_demo/backend/datacloud_service/worker.py` | 新增常量、新增局部变量、新增事件处理分支 |

---

## 验收标准

1. 发起一次数据查询，前端过程日志中依次出现以下四个阶段标题（折叠区块标题）：
   - "问题理解"
   - "任务生成"
   - "任务执行"
   - "结果生成"
2. 四个标题出现顺序与图节点执行顺序一致，不乱序。
3. `execution` 节点循环多次时，"任务执行"标题只出现一次。
4. 每个阶段标题下的 `think_text` 内容归属正确（不跨阶段混入）。
5. 原有功能不受影响，最终答案内容不变。
