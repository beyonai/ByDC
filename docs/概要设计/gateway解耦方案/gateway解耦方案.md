# Gateway 解耦方案：by-datacloud 移除 by-framework 依赖

**文档版本：** v2.0  
**日期：** 2026-04-29  

---

## 一、背景与问题

`by-datacloud`（`datacloud-analysis`、`datacloud-data`、`datacloud-knowledge`）定位为**可独立发布的业务 SDK**，应与具体部署框架解耦，在不同的 Gateway 运行时下均可复用。

当前 `datacloud-analysis` 的三处文件在运行时依赖 `by-framework` 的协议类型：

| 文件 | 依赖 API |
|------|---------|
| `orchestration/respond/formatter.py` | `StreamChunkEvent`, `EventType`, `SseMessageType` |
| `orchestration/execution/react_loop.py` | `StreamChunkEvent`, `EventType`, `SseMessageType`, `SseReasonMessageType` |
| `orchestration/execution/tool_wrapper.py` | `StreamChunkEvent` |

这些导入的目的只有一个：**向 `gateway_context` 推送 SSE 流式事件**（thinking token、answer token、数据表格）。

当前三个子包的依赖声明：

| 子包 | by-framework 声明 | 实际导入 |
|------|-----------------|---------|
| `datacloud-analysis` | `>=0.1.2`（pyproject.toml） | 有（3 个文件，懒导入） |
| `datacloud-data` | 无 | 无 |
| `datacloud-knowledge` | 无 | 无 |

**解耦工作范围仅限于 `datacloud-analysis`**。

---

## 二、被使用的 by_framework API

### 2.1 emit 调用的完整签名

三处文件中所有 `emit_chunk` 调用均形如：

```python
await gateway_context.emit_chunk(
    StreamChunkEvent(content=text),
    event_type=EventType.ANSWER_DELTA.value,        # 字符串 "answer_delta"
    content_type=SseMessageType.text.value,          # 字符串 "text"
    message_id=message_id,
    parent_message_id=parent_message_id,             # 可选
)
```

### 2.2 使用到的字符串常量

| API | 实际字符串值 | 用途 |
|-----|------------|------|
| `EventType.ANSWER_DELTA.value` | `"answer_delta"` | 最终答案流 |
| `EventType.REASONING_LOG_DELTA.value` | `"reasoning_log_delta"` | thinking/推理 token |
| `EventType.REASONING_LOG_START.value` | `"reasoning_log_start"` | thinking 完成通知 |
| `SseMessageType.text.value` | `"text"` | 纯文本答案 |
| `SseMessageType.data_table_json.value` | `"6001"` | 数据表格 JSON |
| `SseReasonMessageType.think_text.value` | `"think_text"` | 思考过程文本 |

`StreamChunkEvent` 本质是只有 `content: str` 字段的数据容器。

---

## 三、设计目标

1. `by-datacloud` 三个子包的 `pyproject.toml` 均不声明 `by-framework` 依赖。
2. `by-datacloud` 源码不出现任何 `from by_framework import ...` 语句。
3. `by_framework` 只保留在落地项目 `byclaw-data` 一侧。
4. `byclaw-data` 对 `by-datacloud` 的调用方式保持不变，改动最小化。
5. 不破坏现有测试。

---

## 四、方案：以 LangGraph Custom Event 替代直接回调

### 4.1 核心思路

当前模式是**图节点内直接回调**：节点在执行过程中调用注入的 `gateway_context.emit_chunk()`，将 SSE 事件从 SDK 内部向外推送。这造成了 `datacloud-analysis` 对 `by_framework` 协议类型的依赖。

新方案改为 **LangGraph Custom Event 上浮**：节点通过 LangGraph 内置的 `adispatch_custom_event()` 将流式 chunk 作为自定义事件发布，`worker.py` 已经在消费 `astream_events()` 事件流，在顶层统一接收并转发给 SSE。

```
【当前模式 — 节点内直接回调，耦合 by_framework】

  react_loop.py (LangGraph 节点内)
    │  from by_framework import StreamChunkEvent, EventType   ← 耦合点
    └─ await gateway_context.emit_chunk(StreamChunkEvent(...), ...)
                │
                └─ ByclawDataClarification.emit_chunk()
                      └─ by_framework emitter → SSE


【新方案 — Custom Event 上浮，by-datacloud 零耦合】

  react_loop.py (LangGraph 节点内)
    │  from langchain_core.callbacks import adispatch_custom_event  ← 只依赖 langchain-core
    └─ await adispatch_custom_event("dc_stream_chunk", {
           "content": token,
           "event_type": "reasoning_log_delta",
           "content_type": "think_text",
           "message_id": message_id,
       })
         │
         │  LangGraph astream_events 管道（已有）
         ▼
  worker.py  _stream_graph()
    │  async for event in target_graph.astream_events(..., version="v2"):
    │      if event["event"] == "on_custom_event"
    │         and event["name"] == "dc_stream_chunk":
    └─        await context.emit_chunk(StreamChunkEvent(d["content"]), ...)
                    │
                    └─ by_framework emitter → SSE
```

`worker.py` 成为**唯一知道 `by_framework` 协议类型的地方**。

---

### 4.2 Custom Event 规范

**事件名（固定）：** `"dc_stream_chunk"`

**Payload 结构：**

```python
{
    "content":          str,   # 必填：文本内容（已经过 coerce_stream_chunk_text 处理）
    "event_type":       str,   # 必填：见下表
    "content_type":     str,   # 必填：见下表
    "message_id":       str,   # 必填：同一轮推送共享同一 ID
    "parent_message_id": str,  # 可选，默认 ""，tool_wrapper 中使用
}
```

**字符串常量（与 by_framework 保持一致，前端无感知）：**

| 场景 | event_type | content_type |
|------|-----------|-------------|
| thinking / 推理 token | `"reasoning_log_delta"` | `"think_text"` |
| thinking 完成通知 | `"reasoning_log_start"` | `"think_text"` |
| 最终答案 token | `"answer_delta"` | `"text"` |
| 数据表格（6001 分块） | `"answer_delta"` | `"6001"` |

---

### 4.3 `datacloud-analysis` 侧修改

#### 4.3.1 `react_loop.py` — 替换 4 个 emit 函数

**Before（当前）：**
```python
async def _emit_thinking_token(gateway_context: Any, token: str, *, message_id: str) -> None:
    if not gateway_context or not token:
        return
    try:
        from by_framework import EventType, StreamChunkEvent  # type: ignore
        from by_framework.core.protocol.content_type import SseReasonMessageType  # type: ignore
        from datacloud_data_sdk.stream_text import coerce_stream_chunk_text  # type: ignore

        await gateway_context.emit_chunk(
            StreamChunkEvent(content=coerce_stream_chunk_text(token)),
            event_type=EventType.REASONING_LOG_DELTA.value,
            content_type=SseReasonMessageType.think_text.value,
            message_id=message_id,
        )
    except Exception as exc:
        logger.debug("[react_loop] thinking_token emit failed: %s", exc)
```

**After（修改后）：**
```python
async def _emit_thinking_token(token: str, *, message_id: str) -> None:
    # gateway_context 参数移除：不再需要，通过 LangGraph Custom Event 上浮
    if not token:
        return
    try:
        from langchain_core.callbacks import adispatch_custom_event
        from datacloud_data_sdk.stream_text import coerce_stream_chunk_text  # type: ignore

        await adispatch_custom_event("dc_stream_chunk", {
            "content": coerce_stream_chunk_text(token),
            "event_type": "reasoning_log_delta",
            "content_type": "think_text",
            "message_id": message_id,
        })
    except Exception as exc:
        logger.debug("[react_loop] thinking_token emit failed: %s", exc)
```

同理替换 `_emit_stream_token`、`_emit_answer_token`、`_emit_thinking_done_notification`，
调整对应的 `event_type` / `content_type` 字符串（见 4.2 节常量表）。

#### 4.3.2 `formatter.py` — 替换 4 个 emit 函数

`_emit_text`、`_emit_json_as_6001`、`_stream_csv_as_6001`、`_emit_query_result_as_6001` 中的
`gateway_context.emit_chunk(StreamChunkEvent(...), ...)` 统一替换为
`adispatch_custom_event("dc_stream_chunk", {...})`，并移除 `gateway_context` 参数。

#### 4.3.3 `tool_wrapper.py` — 替换 2 个 emit 函数

`_emit_think`、`_emit_child_think` 中构造 `StreamChunkEvent` 的部分改为直接传 `str`，
通过 `adispatch_custom_event` 上浮，移除 `StreamChunkEvent` 导入。

#### 4.3.4 `gateway_context` 注入的保留说明

`gateway_context` 通过 `config["configurable"]["gateway_context"]` 注入，**仍然保留**，原因：

- `user_clarify_node.py` 使用 `gateway_context.complex_ask_user()` 实现用户澄清中断，这是**控制流**而非事件流，不适合通过 Custom Event 处理。
- 只有 **emit 类操作**（纯数据推送）迁移到 Custom Event；**控制类操作**保持原有注入模式。

迁移完成后，`react_loop.py` / `formatter.py` / `tool_wrapper.py` 中的 `gateway_context` 参数将只传向控制流路径，不再用于 emit。

---

### 4.4 `worker.py` 侧修改

在 `_stream_graph()` 的 `astream_events` 事件循环中增加 `on_custom_event` 分支：

```python
# worker.py — _stream_graph() 事件循环，新增分支
elif kind == "on_custom_event" and event.get("name") == "dc_stream_chunk":
    d: dict[str, Any] = event.get("data") or {}
    _content = d.get("content", "")
    _event_type = d.get("event_type", "")
    _content_type = d.get("content_type", "")
    _msg_id = d.get("message_id", "")
    _parent_msg_id = d.get("parent_message_id", "")

    emit_kwargs: dict[str, Any] = {
        "event_type": _event_type,
        "content_type": _content_type,
        "message_id": _msg_id,
    }
    if _parent_msg_id:
        emit_kwargs["parent_message_id"] = _parent_msg_id

    await context.emit_chunk(
        StreamChunkEvent(content=_content),
        **emit_kwargs,
    )
```

这段代码放在 `kind == "on_chain_start"` 分支**之前**，与现有结构保持一致。

---

### 4.5 更新 `pyproject.toml`

**`packages/datacloud-analysis/pyproject.toml`**：删除 `"by-framework>=0.1.2"`。

**根 `pyproject.toml`**：删除 `"by-framework>=0.1.13"`（`by-framework` 的依赖声明保留在 `byclaw-data` 的 `pyproject.toml` 中）。

---

## 五、实施步骤

### Step 1：修改 `react_loop.py`

将 4 个 `_emit_*` 函数中的 `gateway_context.emit_chunk(StreamChunkEvent(...), ...)` 全部替换为 `adispatch_custom_event("dc_stream_chunk", {...})`，移除 `gateway_context` 参数。

### Step 2：修改 `formatter.py`

将 `_emit_text`、`_emit_json_as_6001`、`_stream_csv_as_6001`、`_emit_query_result_as_6001` 中的 emit 调用替换，移除 `gateway_context` 参数及 `by_framework` 懒导入。

### Step 3：修改 `tool_wrapper.py`

将 `_emit_think`、`_emit_child_think` 中的 `StreamChunkEvent` 构造替换为 `adispatch_custom_event`，移除 `by_framework` 导入。

### Step 4：更新 `pyproject.toml`

删除 `datacloud-analysis` 及根包中的 `by-framework` 依赖声明。

### Step 5：修改 `worker.py`

在 `_stream_graph()` 的 `astream_events` 循环中增加 `on_custom_event / dc_stream_chunk` 分支（约 15 行）。

### Step 6：验证

```bash
# by-datacloud 侧：确认无 by_framework 导入
grep -r "by_framework" packages/datacloud-analysis/src/
# 预期：无输出

# 类型检查 + Lint
uv run ruff format packages/datacloud-analysis/src
uv run ruff check packages/datacloud-analysis/src
uv run mypy packages/datacloud-analysis/src

# 单元测试
uv run pytest packages/datacloud-analysis/tests

# byclaw-data 侧：集成测试
cd D:\data\code\baiying\byclaw-all\byclaw-data
uv run pytest
```

---

## 六、影响范围评估

### 不受影响

| 项目 | 原因 |
|------|------|
| `datacloud-data`、`datacloud-knowledge` | 无 `by_framework` 导入 |
| `byclaw-data/worker.py` 现有逻辑 | 只新增一个 `elif` 分支，不改动现有分支 |
| `byclaw-data` 中断/澄清流程 | `gateway_context` 注入保留，`complex_ask_user()` 路径不变 |
| 前端 SSE 协议 | 字符串值 `"answer_delta"`、`"6001"`、`"think_text"` 完全一致 |
| 测试文件（`test_worker_resume_regressions.py` 等） | 测试专用 `try/except ImportError` 不受影响 |

### 需修改

| 位置 | 文件数 | 改动量 |
|------|--------|-------|
| `datacloud-analysis`：替换 emit 函数 | 3 | 每处 1~2 个 import + emit 调用替换 |
| `datacloud-analysis`：`pyproject.toml` | 2 | 删除 1 行 |
| `byclaw-data`：`worker.py` 新增分支 | 1 | 约 15 行 |

**`byclaw-data` 侧无需修改 `ByclawDataClarification`，无需增加适配层。**

---

## 七、方案对比

| 维度 | v1.0（protocol 子包） | v2.0（LangGraph Custom Event） |
|------|---------------------|-------------------------------|
| 解耦彻底性 | 引入自定义 `StreamChunk` 类，接口仍然耦合 | **节点不感知任何 SSE 概念，彻底解耦** |
| byclaw-data 改动 | 需要在 `emit_chunk` 中做类型适配 | **只需在已有事件循环中加 `elif` 分支** |
| 新增代码量 | 新增 4 个 protocol 文件 | **无新文件，纯替换** |
| 架构一致性 | 混合两种推送路径 | **统一走 LangGraph 事件管道** |
| 测试友好性 | 节点仍依赖 context 对象 | **节点完全无副作用依赖，单元测试更简洁** |
| 风险 | 低（最小改动） | 低（`adispatch_custom_event` 是 `langchain-core` 稳定 API，`langchain_core.callbacks` 导出） |

---

## 八、后续：`by-datacloud` 作为纯 SDK 发布

解耦完成后，`by-datacloud` 可作为**与任何 Gateway 运行时无关的纯分析 SDK** 发布到内部 PyPI。

任何消费方只需在 `astream_events()` 循环中处理 `on_custom_event / dc_stream_chunk` 事件，即可获得完整的流式推送能力，无需修改 SDK 本身。

```
# byclaw-data pyproject.toml（解耦后）
dependencies = [
    "by-framework>=0.1.13",   # Gateway 运行时，只在落地项目声明
    "datacloud-analysis",      # 纯业务 SDK，零 by-framework 依赖
    ...
]
```
