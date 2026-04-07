# 中断恢复机制规范文档

**版本**: v2.1  
**日期**: 2026-04-07  
**范围**: `datacloud-analysis` 包工具层 + `datacloud_service` Worker 层

---

## 1. 设计原则

所有需要等待外部响应（用户输入、子 Agent 回调、异步任务完成等）的工具，
统一继承 `InterruptibleTool` 基类，只实现**业务逻辑**，不感知中断/恢复的机制细节。

**分层职责：**

| 层 | 职责 |
|---|---|
| **工具子类** | 构造 interrupt payload；实现 `_dispatch_side_effect` 执行副作用；处理 resume 数据 |
| **`InterruptibleTool` 基类** | 按固定顺序编排：调用子类构造→调用子类副作用→调用 `interrupt()`→包装 `ResumeData`→调用子类 resume 处理 |
| **Worker `_stream_graph`** | 检测 `snapshot.interrupts`，按 `reason_code` 执行 Worker 侧响应（如推前端） |

**核心设计决策：副作用在工具基类中执行，不在 Worker 中执行**

Worker 不需要从 interrupt payload 中读取副作用参数自行调用。副作用参数（`side_effect_kwargs`）
由工具基类在 `_dispatch_side_effect` 中使用，**不写入 checkpoint**，通过稳定 hash ID 保证幂等。

---

## 2. LangGraph 中断恢复原理

`interrupt(payload)` 本质是抛出 `GraphInterrupt`，Pregel 将 payload 写入 checkpoint 的
`__interrupt__` channel，图挂起。

恢复时调用 `graph.astream(Command(resume=value), config)`，Pregel 加载同一 checkpoint，
**从头重新执行被中断的节点**。再次碰到同一 `interrupt()` 调用点时，发现已有 resume value，
直接返回，不再抛异常。

**关键约束：Node Restart**——`interrupt()` 之前的所有代码都会在 resume 时再次执行，
副作用会重复触发。

**应对方案**：副作用（如 `call_agent`）使用稳定的 `message_id`（基于业务内容 hash），
框架侧凭 `message_id` 去重，保证幂等。

> **前提**：框架侧 `call_agent` 必须支持基于 `message_id` 的幂等去重（同一 `message_id`
> 重复提交时忽略而非重启子 Agent）。此为整个设计的外部依赖。

---

## 3. 核心基类规范

### 3.1 类结构

```
packages/datacloud-analysis/src/datacloud_analysis/tools/base/
├── __init__.py           # 导出 InterruptibleTool, BeforeInterruptResult, ResumeData
└── interruptible.py      # 核心实现
```

### 3.2 子类需实现三个方法

```python
from datacloud_analysis.tools.base import BeforeInterruptResult, InterruptibleTool, ResumeData

class MyAsyncTool(InterruptibleTool):

    async def _build_interrupt_payload(self, **kwargs) -> BeforeInterruptResult:
        """
        每次执行都会调用（含 resume 重跑）。必须是纯数据构造，无 I/O 副作用。
        - 选择 reason_code
        - 构造 display（前端展示）
        - 将副作用参数放入 side_effect_kwargs（不写入 checkpoint）
        - 需要幂等的 ID 必须基于业务内容 hash 生成，不能用 uuid4()
        """
        stable_id = _stable_id(key1, key2, ...)
        return BeforeInterruptResult(
            reason_code="ASYNC_TOOL_WAIT",
            display={"job_id": stable_id},
            correlation_id=stable_id,
            side_effect_kwargs={"job_id": stable_id, "params": ...},
        )

    async def _dispatch_side_effect(
        self,
        before: BeforeInterruptResult,
        context: Any,
        **kwargs: Any,
    ) -> None:
        """
        执行实际副作用（I/O）。基类会在 interrupt() 之前调用此方法。
        resume 重跑时也会被调用——依赖 side_effect_kwargs 中的稳定 ID 保证幂等。
        默认实现为空，子类按需覆盖。
        """
        if before.side_effect_kwargs:
            await context.submit_job(**before.side_effect_kwargs)

    async def _handle_resume(self, resume: ResumeData, **kwargs) -> Any:
        """
        resume 数据到达后，返回工具最终输出给 LLM。
        """
        if resume.timed_out:
            return "[任务超时，请重试]"
        if not resume.ok:
            return f"[失败: {resume.error or resume.status}]"
        if resume.data is None:
            return "[任务完成，但未返回数据]"
        return resume.data
```

### 3.3 基类执行流程

```
_arun(**kwargs)
  │
  ├─ 1. _build_interrupt_payload(**kwargs)
  │       └─ 子类返回 BeforeInterruptResult（纯数据，无 I/O）
  │
  ├─ 2. _dispatch_side_effect(before, context, **kwargs)
  │       └─ 子类执行副作用（call_agent、submit_job 等）
  │          首次执行：真正触发外部调用
  │          resume 重跑：稳定 ID 使框架侧去重，不重复触发
  │
  ├─ 3. interrupt(before.to_interrupt_payload())
  │       └─ 首次：抛出 GraphInterrupt，图挂起，checkpoint 写 PG
  │          恢复：直接返回 raw_resume_value
  │
  ├─ 4. ResumeData(raw_resume_value)
  │       └─ 标准化包装，支持 status/data/error/ok/cancelled/timed_out
  │
  └─ 5. _handle_resume(resume, **kwargs)
          └─ 子类处理结果，返回给 LLM
```

### 3.4 `BeforeInterruptResult` 字段说明

| 字段 | 类型 | 说明 |
|---|---|---|
| `reason_code` | `InterruptReasonCode` | 中断类型，Worker 按此分发（不同类型的 Worker 侧响应不同） |
| `display` | `dict` | 前端展示数据，写入 checkpoint |
| `correlation_id` | `str \| None` | 关联外部任务的稳定 ID（如子 Agent message_id），写入 checkpoint |
| `timeout_seconds` | `int \| None` | 超时秒数，写入 checkpoint |
| `side_effect_kwargs` | `dict` | **不写入 checkpoint**，由基类传给 `_dispatch_side_effect` |

`to_interrupt_payload()` 只序列化 `reason_code / display / correlation_id / timeout_seconds`，
`side_effect_kwargs` 永远不进入 checkpoint，也不会在 resume 重跑时从 checkpoint 恢复——
这正是设计意图：副作用参数由 `_build_interrupt_payload` 在每次执行时重新计算。

### 3.5 `ResumeData` 解析规则

```python
# raw 为 dict 时：
resume.status = str(raw.get("status") or "ok")
# data 优先取 "data"，其次取 "conclusion"（子 Agent 返回场景）
# 注意：使用 is not None 而非 or，避免空字符串、0、[] 等 falsy 值被错误丢弃
resume.data   = raw["data"] if "data" in raw else raw.get("conclusion")
resume.error  = raw.get("error")

# raw 为非 dict 时（字符串/裸值）：
resume.status = "ok"
resume.data   = raw

# ok 状态集合：
_OK_STATUSES = {"ok", "done", "completed", "success"}
```

### 3.6 `InterruptReasonCode` 枚举

```python
InterruptReasonCode = Literal[
    "ASK_USER",            # 向用户提问，Worker 侧需推前端 ask_user 事件
    "CONFIRM_ACTION",      # 执行前确认，Worker 侧需推前端确认 UI
    "ASYNC_TOOL_WAIT",     # 等待异步任务完成，Worker 侧静默等待
    "AGENT_DELEGATE_WAIT", # 子 Agent 委派等待，Worker 侧静默等待
    "APPROVAL_GATE",       # 审批节点，Worker 侧需推前端审批 UI
]
```

---

## 4. `AGENT_DELEGATE_WAIT` 完整流程

### 4.1 端到端时序

```
【父 Agent：工具首次执行】

LLM 生成 DelegateToAgentTool tool_call
  └─ DelegateToAgentTool._arun(content="...", _context=gateway_context)
       │
       ├─ _build_interrupt_payload()                     ← 纯数据，无 I/O
       │    └─ stable_message_id = sha1(target:content:session_id)[:16]
       │    └─ call_agent_kwargs = {target_agent_type, content,
       │                            message_id=stable_message_id, metadata, ...}
       │    └─ return BeforeInterruptResult(
       │         reason_code="AGENT_DELEGATE_WAIT",
       │         display={target_agent_type, delegate_content},
       │         correlation_id=stable_message_id,
       │         side_effect_kwargs=call_agent_kwargs,
       │       )
       │
       ├─ _dispatch_side_effect(before, context)         ← 真正发起调用
       │    └─ await context.call_agent(**call_agent_kwargs)
       │         └─ 子 Agent 提交到队列异步执行
       │
       └─ interrupt({"reason_code": "AGENT_DELEGATE_WAIT",
                     "display": {...},
                     "correlation_id": stable_message_id})
            └─ 图挂起，checkpoint 写 PG

【父 Agent Worker：检测中断】

_stream_graph
  └─ await aget_state() → snapshot.interrupts[0].value["reason_code"]
  └─ == "AGENT_DELEGATE_WAIT"
  └─ 静默等待，return {"status": "waiting"}
       （不推前端，不调 ask_user，也不需要读取 call_agent_kwargs）

【子 Agent：执行完成】

子 Agent worker._stream_graph 正常完成
  └─ process_result = {"status": "done", "conclusion": "子Agent最终回复"}
  └─ command.header.metadata 含 resume 信息（parent_resume_target）
  └─ _enqueue_agent_return(command, status="completed", reply_data=process_result)
       └─ 构造 ResumeCommand，发往父 Agent session

【父 Agent Worker：处理 ResumeCommand】

process_command(ResumeCommand)
  └─ resume_value = command.reply_data   # {"status": "done", "conclusion": "..."}
  └─ 从 header.metadata 读取 checkpoint_id / checkpoint_ns 定位恢复点
  └─ graph_input = Command(resume=resume_value)
  └─ 调用 _stream_graph(graph_input=Command(resume=...))

【父 Agent：工具 resume 重跑（Node Restart）】

DelegateToAgentTool._arun()（节点从头重跑）
  ├─ _build_interrupt_payload()          ← 再次调用，stable_message_id 不变
  ├─ _dispatch_side_effect()
  │    └─ context.call_agent(message_id=stable_message_id)
  │         └─ 框架侧：message_id 已存在 → 去重，子 Agent 不重复启动
  └─ interrupt(payload)
       └─ 此时有 resume value → 直接返回 {"status": "done", "conclusion": "..."}

DelegateToAgentTool._handle_resume(resume)
  └─ resume.ok == True（status="done" ∈ _OK_STATUSES）
  └─ resume.data == "子Agent最终回复"（"data" 键不存在，取 "conclusion"）
  └─ return "子Agent最终回复"   ← LLM 看到工具结果，继续执行
```

### 4.2 metadata 传递规范

子 Agent `call_agent` 时，`metadata` 中必须包含以下字段，供子 Agent 完成后构造回调：

```python
metadata = {
    # 子 Agent 完成后构造 ResumeCommand 所需的父 Agent 定位信息
    "parent_resume_target": {
        "session_id":   parent_session_id,
        "agent_id":     parent_agent_id,
        "resume_via":   "ResumeCommand.reply_data",
        "interrupt_reason": "AGENT_DELEGATE_WAIT",
        "delegate_parent_message_id": delegate_parent_message_id,
    },
    # 父 Agent 恢复所需的 checkpoint 定位字段（由 Worker 层在发起调用时注入）
    "resume_checkpoint_id":  parent_checkpoint_id,   # 中断时的 checkpoint ID
    "resume_checkpoint_ns":  parent_checkpoint_ns,   # 中断时的 checkpoint namespace
    "resume_thread_id":      parent_thread_id,       # 父 Agent 的 LangGraph thread ID
    # 其他父 Agent 身份信息
    "delegate_parent_message_id": delegate_parent_message_id,
    "resume_agent_id":   parent_agent_id,
    "resume_agent_name": parent_agent_name,
    "resume_agent_type": parent_runtime_agent_type,
    "resume_conf_hash":  parent_conf_hash,
}
```

> **注意**：`resume_checkpoint_id` 和 `resume_checkpoint_ns` 必须由工具侧或 Worker 侧在发起
> 调用时填入（从当前 snapshot.config 中读取），不能依赖父 Agent 稍后才写入 checkpoint 的值。
> Worker 的 `_resolve_resume_checkpoint_target` 优先读取 `resume_checkpoint_id`，
> 其次读取 `plain_checkpoint_id`（当且仅当无 `resume_thread_id` 时）。
> 若 metadata 同时携带 `resume_thread_id` 和 `plain_checkpoint_id` 而无 `resume_checkpoint_id`，
> Worker 会忽略 `plain_checkpoint_id` 并从 thread 最新 checkpoint 恢复——这是故意的降级行为，
> 但使用方应尽量提供 `resume_checkpoint_id` 以精确定位。

---

## 5. 新增工具规范（How to add a new interruptible tool）

### 5.1 步骤

**Step 1**：继承 `InterruptibleTool`，实现三个方法。

**Step 2**：`_build_interrupt_payload` 中：
- 选择对应的 `reason_code`
- 将副作用参数放入 `side_effect_kwargs`（不会进 checkpoint）
- 需要幂等的 ID **必须**用业务内容 hash 生成，不能用 `uuid4()`

**Step 3**：`_dispatch_side_effect` 中：
- 执行真正的 I/O 副作用
- 不需要写 I/O 时可不覆盖（基类默认空实现）

**Step 4**：`_handle_resume` 中：
- 检查 `resume.ok` / `resume.cancelled` / `resume.timed_out`
- 从 `resume.data` 取结果返回给 LLM

**Step 5**：在 Worker `_stream_graph` 中断处理区域，添加对应 `reason_code` 的 Worker 侧响应。

### 5.2 Worker 侧中断处理结构

```python
# worker.py _stream_graph 中断处理
if interrupt_reason == "AGENT_DELEGATE_WAIT":
    # 副作用已由工具基类执行，Worker 静默等待即可
    return {"status": "waiting"}

elif interrupt_reason == "ASYNC_TOOL_WAIT":
    # 副作用已由工具基类执行，Worker 静默等待即可
    return {"status": "waiting"}

elif interrupt_reason in ("ASK_USER", "CONFIRM_ACTION", "APPROVAL_GATE"):
    # 需要推前端
    await context.ask_user(AskUserEvent(
        prompt=prompt,
        metadata={
            "thread_id": ...,
            "checkpoint_id": checkpoint_id,
            "checkpoint_ns": checkpoint_ns,
            "interrupt_reason": interrupt_reason,
            ...
        },
    ))
    return {"status": "waiting"}

else:
    # 未知类型：按需扩展，默认推前端兜底
    await context.ask_user(...)
    return {"status": "waiting"}
```

### 5.3 示例：`ASYNC_TOOL_WAIT`（等待异步任务）

```python
import hashlib
import json
from typing import Any
from datacloud_analysis.tools.base import BeforeInterruptResult, InterruptibleTool, ResumeData


def _stable_id(*parts: str) -> str:
    raw = ":".join(parts)
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


class AsyncJobTool(InterruptibleTool):
    name: str = "async_job"
    description: str = "提交异步任务并等待结果"

    async def _build_interrupt_payload(
        self, job_params: dict, _context: Any = None, **kwargs: Any
    ) -> BeforeInterruptResult:
        session_id = str(getattr(_context, "session_id", ""))
        stable_job_id = _stable_id(json.dumps(job_params, sort_keys=True), session_id)

        return BeforeInterruptResult(
            reason_code="ASYNC_TOOL_WAIT",
            display={"job_id": stable_job_id, "params": job_params},
            correlation_id=stable_job_id,
            side_effect_kwargs={
                "job_id": stable_job_id,
                "params": job_params,
            },
        )

    async def _dispatch_side_effect(
        self,
        before: BeforeInterruptResult,
        context: Any,
        **kwargs: Any,
    ) -> None:
        if before.side_effect_kwargs and context is not None:
            await context.submit_async_job(**before.side_effect_kwargs)

    async def _handle_resume(self, resume: ResumeData, **kwargs: Any) -> Any:
        if resume.timed_out:
            return "[任务超时，请重试]"
        if not resume.ok:
            return f"[任务失败: {resume.error or resume.status}]"
        if resume.data is None:
            return "[任务完成，但未返回数据]"
        return resume.data
```

---

## 6. 幂等保障规范

所有 `InterruptibleTool` 子类，`side_effect_kwargs` 中的关键 ID（`message_id`、`job_id` 等）**必须**：

1. 基于 `(业务参数, session_id)` 的确定性 hash 生成
2. 使用 `hashlib.sha1(raw.encode()).hexdigest()[:16]`（16 位）
3. **禁止**使用 `uuid4()` 或任何随机生成方式

理由：LangGraph resume 时节点从头重跑，`_dispatch_side_effect` 会被调用两次。
稳定 ID 使框架侧能够识别并去重，避免重复启动子 Agent 或重复提交任务。

**框架侧责任**：`context.call_agent` 和其他异步提交接口，必须对相同 `message_id` 的重复
调用执行幂等去重（忽略或返回已有结果），这是此设计的**外部依赖**。

---

## 7. 测试规范

每个 `InterruptibleTool` 子类需要三类测试用例：

### 7.1 功能测试

验证：
- `_dispatch_side_effect` 中的副作用方法（`call_agent` 等）被调用一次
- interrupt payload **不含** `side_effect_kwargs` 内容（不污染 checkpoint）
- `_handle_resume` 正确处理 ok / error / timed_out / None data 四种情况
- resume 结果正确返回给 LLM

### 7.2 幂等测试

验证相同入参两次调用产生相同的 `correlation_id` / `message_id`：

```python
async def test_xxx_idempotent_same_id():
    tool = MyTool(...)
    context = FakeContext()
    fake_resume = {"status": "done", "data": "result"}

    ids = []
    def fake_interrupt(payload):
        ids.append(payload.get("correlation_id"))
        return fake_resume

    with patch("...interrupt", side_effect=fake_interrupt):
        await tool._arun(..., _context=context)
    with patch("...interrupt", side_effect=fake_interrupt):
        await tool._arun(..., _context=context)

    assert ids[0] == ids[1], "resume 重跑时 correlation_id 必须稳定"
```

### 7.3 payload 隔离测试

验证 `side_effect_kwargs` 不出现在 interrupt payload 中：

```python
async def test_side_effect_kwargs_not_in_payload():
    captured = {}
    def fake_interrupt(payload):
        captured.update(payload)
        return {"status": "done", "data": "ok"}

    with patch("...interrupt", side_effect=fake_interrupt):
        await tool._arun(...)

    assert "side_effect_kwargs" not in captured
    # 副作用参数中的敏感字段也不应出现在 payload 顶层
    assert "call_agent_kwargs" not in captured
```

---

## 8. 已实现工具清单

| 工具类 | reason_code | 文件 | 副作用 |
|---|---|---|---|
| `DelegateToAgentTool` | `AGENT_DELEGATE_WAIT` | `tools/delegate.py` | `context.call_agent(...)` |

---

## 9. 已知限制与风险

| 风险 | 影响 | 缓解方案 |
|---|---|---|
| Node Restart 导致 `_dispatch_side_effect` 调用两次 | 子 Agent 重复启动 | 稳定 hash ID + 框架侧 `message_id` 去重（**外部依赖**）|
| 子 Agent 回调丢失（网络/宕机） | 父 Agent 永久挂起 | 需超时机制（`timeout_seconds`，out of scope）|
| 并行工具调用中多个 `interrupt()` | LangGraph open bug #6533 | 避免并行调用多个可中断工具 |
| `context.call_agent` 不支持 `message_id` 去重 | resume 重跑时子 Agent 重复启动 | 框架侧必须实现幂等，否则不能使用此设计 |
| checkpoint 定位不精确（无 `resume_checkpoint_id`） | 恢复到错误节点 | 工具侧/Worker 侧发起 call_agent 时注入 `resume_checkpoint_id` |
