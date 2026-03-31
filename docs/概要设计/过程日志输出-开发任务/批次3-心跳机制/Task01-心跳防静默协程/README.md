# Task01 - 心跳机制（防静默）

## 任务概述

在 `worker.py` 的 `_stream_graph` 方法中，增加独立心跳协程，当超过 3 秒无任何过程日志输出时，自动推送一条心跳 `think_text`，保障前端始终有内容更新，避免用户误以为系统卡死。

---

## 背景

当前心跳方案（在 `async for event` 循环内检查时间差）存在根本缺陷：`astream_events` 在等待下一个事件时会阻塞，若图内部长时间不产生任何事件，循环不会推进，心跳也不会触发。

正确做法是用 `asyncio.create_task` 启动独立心跳协程，与主事件流并行运行。

---

## 开发内容

### 1. 新增常量

文件：`datacloud_service/worker.py`（模块顶层）

```python
_HEARTBEAT_INTERVAL: float = 3.0  # 秒，超过此时间无输出则发一条心跳

_HEARTBEAT_MESSAGES: list[str] = [
    "数据量较大，正在处理中...",
    "查询较复杂，请耐心等待...",
    "正在整合多维度数据...",
    "即将完成，请稍候...",
]
```

### 2. 新增心跳协程函数

```python
async def _heartbeat_loop(
    context: Any,
    stop_event: asyncio.Event,
    last_emit_time_ref: list[float],  # 用列表包装以便跨协程共享引用
) -> None:
    """独立心跳协程，每隔 _HEARTBEAT_INTERVAL 秒检查一次，若无输出则推送心跳。"""
    idx = 0
    while not stop_event.is_set():
        await asyncio.sleep(1.0)
        now = asyncio.get_event_loop().time()
        if now - last_emit_time_ref[0] >= _HEARTBEAT_INTERVAL:
            msg = _HEARTBEAT_MESSAGES[idx % len(_HEARTBEAT_MESSAGES)]
            await context.emit_chunk(
                StreamChunkEvent(content=msg),
                event_type=EventType.REASONING_LOG_START.value,
                content_type=SseReasonMessageType.think_text.value,
            )
            last_emit_time_ref[0] = now
            idx += 1
```

### 3. 在 `_stream_graph` 中启动和停止心跳协程

在进入 `astream_events` 循环前启动：

```python
_last_emit_time: list[float] = [asyncio.get_event_loop().time()]
_heartbeat_stop = asyncio.Event()
_heartbeat_task = asyncio.create_task(
    _heartbeat_loop(context, _heartbeat_stop, _last_emit_time)
)
```

在每次推送过程日志后更新时间戳：

```python
# 在每个 emit_chunk 调用后追加：
_last_emit_time[0] = asyncio.get_event_loop().time()
```

在 `astream_events` 循环结束后（`finally` 块）停止心跳：

```python
finally:
    _heartbeat_stop.set()
    _heartbeat_task.cancel()
    try:
        await _heartbeat_task
    except asyncio.CancelledError:
        pass
```

---

## 涉及文件

| 文件 | 改动类型 |
|------|---------|
| `examples/e_commerce_demo/backend/datacloud_service/worker.py` | 新增常量、新增协程函数、修改 `_stream_graph` 启动/停止逻辑 |

---

## 验收标准

1. 模拟一个耗时较长（> 3 秒）的工具调用，前端在 3 秒内收到心跳消息（如"数据量较大，正在处理中..."）。
2. 心跳消息按轮转顺序出现，不重复连续出现同一条。
3. 图执行完成后，心跳协程正常停止，不产生额外输出。
4. 心跳协程异常（如 `CancelledError`）不影响主流程，不导致请求报错。
5. 原有功能不受影响，最终答案内容不变。
