# OpenClaw Gateway 下一阶段工作计划 (A + C 方案) - 修订版

## 关键洞察

基于源码深度分析，以下能力**已经存在**，无需重新实现：

| 能力 | 已有实现 | 说明 |
|------|---------|------|
| **工具沙箱** | deepagents 内置 | `create_deep_agent(tools=..., sandbox=True)` |
| **子 Agent** | deepagents SubAgent | `subagents=[...]` 参数，自动管理 |
| **中断恢复** | LangGraph interrupt/Command | `interrupt()` + `Command(resume=...)` |
| **流式输出** | deepagents astream | 原生支持 |
| **Checkpoint** | LangGraph InMemorySaver | STEER 模式基础 |
| **令牌计数** | AIMessage.usage_metadata | 从模型返回直接提取 |

**真正需要做的**：
1. 将模拟代码替换为实际的 deepagents 集成
2. 从 AIMessage 提取 usage_metadata 实现令牌计数
3. 完善队列策略（SUMMARIZE/INTERRUPT 等）

---

## 方案概述

**目标**: 使系统真正可用 + 添加高级功能  
**实际工作量**: **1.5-2 周**（原估计 4-5 周，因复用现有能力而大幅减少）  
**工作目录**: `/home/luoyanzhuo/project/whale_datacloud-worktrees/openclaw-gateway-implementation`

---

## Wave 1: 核心功能完善 (1 周)

### 任务 1.1: 集成 deepagents 执行引擎
**优先级**: 🔴 最高  
**时间**: **3-4 天**（原 4-5 天）  
**状态**: 未开始

**当前问题**:
```python
# datacloud_agent/core/runner.py:470-480 (模拟实现)
_agent = self.agent_registry.create_agent(agent_id)
await asyncio.sleep(0.01)  # 模拟执行
return {
    "agent_id": agent_id,
    "messages": messages,
    "response": f"Processed {len(messages)} message(s)",
}
```

**目标实现**:
```python
from deepagents import create_deep_agent
from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.messages import AIMessage

class AgentRunner:
    async def _execute_agent(
        self, 
        session_key: str, 
        messages: list[dict],
        checkpointer: InMemorySaver | None = None
    ) -> dict[str, Any]:
        
        # 从 session_key 解析 agent_id
        parts = session_key.split(":")
        agent_id = parts[3]  # tenant:{tenant_id}:agent:{agent_id}:{session_id}
        
        # 获取 agent 配置
        config = self.agent_registry.get(agent_id)
        
        # 创建带 checkpoint 的 agent（支持 STEER）
        agent = create_deep_agent(
            model=f"{config.provider}:{config.model}",
            system_prompt=config.system_prompt,
            tools=config.tools,  # 复用 deepagents 工具系统
            subagents=config.subagents,  # 复用子 Agent 能力
            checkpointer=checkpointer or InMemorySaver()
        )
        
        # 实际执行
        result = await agent.ainvoke(
            {"messages": messages},
            config={"configurable": {"thread_id": session_key}}
        )
        
        # 提取 usage_metadata（无需 tiktoken）
        usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        for msg in reversed(result["messages"]):
            if isinstance(msg, AIMessage) and msg.usage_metadata:
                usage = {
                    "input_tokens": msg.usage_metadata.get("input_tokens", 0),
                    "output_tokens": msg.usage_metadata.get("output_tokens", 0),
                    "total_tokens": msg.usage_metadata.get("total_tokens", 0),
                }
                break
        
        return {
            "agent_id": agent_id,
            "messages": result["messages"],
            "response": result["content"],
            "usage": usage,  # 真实 token 计数
            "tool_calls": result.get("tool_calls", []),
        }
```

**具体步骤**:
1. [ ] 更新 `AgentRegistry.create_agent()` 返回 `CompiledStateGraph` 而非 dict
2. [ ] 更新 `AgentRunner._execute_agent()` 使用 `deepagents.create_deep_agent()`
3. [ ] 添加流式输出支持 (`agent.astream()`)
4. [ ] 集成工具调用事件流
5. [ ] 从 `AIMessage.usage_metadata` 提取令牌计数

**验收标准**:
- [ ] 测试: `pytest datacloud-agent/tests/test_runner.py -v` 通过
- [ ] 验证: 实际 LLM 调用返回非模拟响应
- [ ] 验证: 工具调用正常工作
- [ ] 验证: usage 字段包含真实 token 计数
- [ ] 集成测试: SDK 端到端测试通过

---

### 任务 1.2: 完善队列模式
**优先级**: 🟡 中  
**时间**: **2-3 天**  
**状态**: 部分实现

**当前状态**:
- ✅ `COLLECT` - 合并消息
- ✅ `STEER` - 使用 LangGraph interrupt 注入
- ⚠️ `STEER_BACKLOG` - 需要完善
- ⚠️ `FOLLOWUP` - 需要完善
- ❌ `INTERRUPT` - 需要实现
- ❌ `QUEUE` - 需要实现

**关键实现**:
```python
from langgraph.types import Command

class AgentRunner:
    async def _steer_run(self, session_key: str, prompt: str) -> bool:
        """STEER 模式: 使用 LangGraph Command(resume=...) 注入消息"""
        if session_key not in self._running_tasks:
            return False
        
        task_info = self._running_tasks[session_key]
        agent = task_info["agent"]
        config = task_info["config"]
        
        # 使用 Command(resume=...) 注入消息
        result = await agent.ainvoke(
            Command(resume=prompt),
            config=config
        )
        
        return True
    
    async def _interrupt_run(self, session_key: str) -> None:
        """INTERRUPT 模式: 取消当前运行"""
        if session_key in self._running_tasks:
            task = self._running_tasks[session_key]["task"]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
```

**验收标准**:
- [ ] 测试: `pytest datacloud-agent/tests/test_steer.py -v` 通过
- [ ] 验证: STEER 使用 `Command(resume=...)` 正确注入
- [ ] 验证: INTERRUPT 正确取消运行
- [ ] 验证: STEER_BACKLOG 同时注入和入队

---

### 任务 1.3: 完善队列丢弃策略
**优先级**: 🟡 中  
**时间**: **1-2 天**  
**状态**: 部分实现

**当前状态**:
- ✅ `DropPolicy.OLD` - 丢弃最旧消息
- ✅ `DropPolicy.NEW` - 拒绝新消息
- ❌ `DropPolicy.SUMMARIZE` - 未实现

**SUMMARIZE 实现**:
```python
elif policy == DropPolicy.SUMMARIZE:
    # 使用 LLM 总结最旧的 N 条消息
    messages_to_summarize = queue.messages[:5]
    
    # 调用轻量级模型进行总结
    summary_agent = create_deep_agent(
        model="anthropic:claude-3-haiku",  # 使用轻量模型
        system_prompt="Summarize these messages concisely."
    )
    summary_result = await summary_agent.ainvoke({
        "messages": [{"role": "user", "content": str(messages_to_summarize)}]
    })
    
    # 替换为总结消息
    queue.messages = queue.messages[5:]
    queue.messages.insert(0, QueuedMessage(
        prompt=f"[Summary] {summary_result['content']}",
        session_key=session_key,
        priority=10
    ))
    return True
```

**验收标准**:
- [ ] 测试: `pytest datacloud-agent/tests/test_queue_ops.py -v` 通过
- [ ] 验证: SUMMARIZE 策略正确工作
- [ ] 性能: 总结不阻塞队列操作（异步执行）

---

## Wave 2: 功能扩展 (0.5-1 周)

### 任务 2.1: 配置五个原子工具
**优先级**: 🟡 中  
**时间**: **0.5-1 天**（原 2-3 天）  
**状态**: 未开始

**说明**: 复用 deepagents 工具系统，无需自建沙箱  
**注意**: deepagents 已内置 `write_todos`, `ls`, `read_file`, `write_file`, `execute`, `task` 等工具

**实现**:
```python
# 只需配置业务相关工具（know/query/compute/render/store）
from langchain_core.tools import Tool

business_tools = [
    Tool(name="know", handler=knowledge_service.query),
    Tool(name="query", handler=data_service.execute),
    Tool(name="compute", handler=compute_service.run),
    Tool(name="render", handler=render_service.generate),
    Tool(name="store", handler=storage_service.save),
]

# 创建 agent 时传入
create_deep_agent(
    tools=business_tools,  # deepagents 自动合并内置工具
    ...
)
```

**验收标准**:
- [ ] 验证: 五个业务工具可正常调用
- [ ] 验证: deepagents 内置工具也可用
- [ ] 测试: 工具集成测试通过

---

### 任务 2.2: 配置子 Agent 支持
**优先级**: 🟡 中  
**时间**: **0.5-1 天**（原 2-3 天）  
**状态**: 未开始

**说明**: 复用 deepagents SubAgent 能力

**实现**:
```python
# 在 AgentConfig 中配置子 Agent
subagents = [
    {
        "name": "researcher",
        "description": "Research specialist",
        "system_prompt": "You are a research expert...",
        "tools": ["web_search"]
    },
    {
        "name": "writer",
        "description": "Content writer",
        "system_prompt": "You are a writing expert...",
    }
]

# 创建 agent 时传入
create_deep_agent(
    subagents=subagents,  # deepagents 自动处理子 Agent 调用
    ...
)
```

**验收标准**:
- [ ] 验证: 子 Agent 可被父 Agent 调用
- [ ] 验证: 子 Agent 工具独立
- [ ] 测试: 子 Agent 集成测试

---

### 任务 2.3: 会话持久化清理
**优先级**: 🟡 中  
**时间**: **1-2 天**（可选）  
**状态**: 未开始

**实现**:
```python
class SessionStore:
    async def delete_session(self, session_id: str) -> None:
        """逻辑删除 + 标记需要压缩"""
        await self._append_delete_marker(session_id)
        self._pending_compaction.add(session_id)
    
    async def _compact_if_needed(self) -> None:
        """后台压缩存储"""
        for session_id in self._pending_compaction:
            await self._compact_session_file(session_id)
```

**验收标准**:
- [ ] 测试: `pytest datacloud-agent/tests/test_backend.py -v` 通过
- [ ] 验证: 删除会话后存储空间释放

---

## 📊 修订后的任务依赖关系

```
Wave 1 (核心功能完善):
├── T1.1: deepagents 集成 (3-4天) [阻塞所有其他任务]
│   ├── 子任务: 替换模拟代码
│   ├── 子任务: 集成 usage_metadata 令牌计数
│   └── 子任务: 流式输出支持
├── T1.2: 队列模式完善 (2-3天) [依赖: T1.1]
│   ├── 子任务: STEER 使用 Command(resume=...)
│   ├── 子任务: INTERRUPT 实现
│   └── 子任务: STEER_BACKLOG 完善
└── T1.3: 队列丢弃策略 (1-2天) [依赖: T1.1]
    └── 子任务: SUMMARIZE 实现

Wave 2 (功能扩展):
├── T2.1: 配置五个原子工具 (0.5-1天) [依赖: T1.1]
├── T2.2: 配置子 Agent 支持 (0.5-1天) [依赖: T1.1]
└── T2.3: 会话持久化清理 (1-2天) [可选]
```

**总工作量**: 1.5-2 周（原 4-5 周）

---

## 🎯 验收标准汇总

### 功能验收
- [ ] deepagents 集成: 实际 LLM 调用工作
- [ ] 令牌计数: 从 `AIMessage.usage_metadata` 提取正确值
- [ ] 队列策略: 所有模式正确工作
- [ ] 五个原子工具: 可正常调用
- [ ] 子 Agent: 父子通信正常
- [ ] STEER 模式: 使用 `Command(resume=...)` 注入

### 测试验收
- [ ] SDK 测试: 350+ 测试通过 (当前 283)
- [ ] Service 测试: 50+ 测试通过 (当前 41)
- [ ] 集成测试: 端到端流程通过

---

## 🚀 启动命令

```bash
# 启动工作会话
/start-work openclaw-gateway-phase2
```

---

## 📝 关键设计决策（修订）

1. **不复刻工具沙箱**: 直接使用 deepagents 内置沙箱
2. **不复刻子 Agent**: 直接使用 deepagents SubAgent
3. **不复刻中断恢复**: 直接使用 LangGraph `interrupt()` + `Command(resume=...)`
4. **不使用 tiktoken**: 直接从 `AIMessage.usage_metadata` 提取令牌计数
5. **重点投入**: deepagents 集成 + 队列策略完善

**预期效果**:
- 减少 **60-70%** 开发工作量（从 4-5 周到 1.5-2 周）
- 更稳定的工具执行
- 与 LangGraph 生态更好兼容
- 无需额外依赖（tiktoken）

---

## ⚠️ 重要注意事项

### 关于令牌计数
- ✅ **推荐**: 从 `AIMessage.usage_metadata` 提取
- ❌ **不推荐**: 使用 tiktoken（额外依赖，且只是估算）
- ⚠️ **注意**: 流式输出时需要累加每个 chunk 的 usage

### 关于 STEER 模式
- 必须使用 `Command(resume=...)` 而非直接修改状态
- 需要 `checkpointer` 支持（`InMemorySaver` 或 `PostgresSaver`）
- `thread_id` 使用 `session_key` 保持一致性

### 关于工具系统
- deepagents 已内置常用工具（文件操作、执行、任务等）
- 只需配置业务相关工具（know/query/compute/render/store）
- 工具自动在 sandbox 中执行
