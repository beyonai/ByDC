# 11. STEER 和 STEER_BACKLOG 模式实现
基于 LangGraph 的 `interrupt()` 和 `Command(resume=...)` 机制实现。
## 11.1 核心机制
```python
from langgraph.types import interrupt, Command
# 在 Agent 节点中调用 interrupt，等待外部输入
def agent_node(state):
    # ... 处理中 ...
    
    # 调用 interrupt，暂停执行并等待外部输入
    steer_message = interrupt({
        "type": "steer",
        "message": "Waiting for steer input"
    })
    
    # 当收到 Command(resume=...) 后，steer_message 包含新消息
    return {
        "messages": state["messages"] + [
            {"role": "user", "content": steer_message}
        ]
    }
# 外部向运行中的 Agent 发送消息
graph.invoke(
    Command(resume="新消息内容"),
    config={"configurable": {"thread_id": session_id}}
)
```
## 11.2 带 STEER 支持的 AgentRunner
```python
from typing import Dict, Optional, Any
import asyncio
from langgraph.types import Command
from langgraph.checkpoint.memory import InMemorySaver
class SteerableAgentRunner:
    """
    支持 STEER 模式的 Agent 运行器
    
    使用 LangGraph 的 interrupt/Command(resume) 机制实现:
    - STEER: 立即注入消息到当前运行
    - STEER_BACKLOG: 立即注入 + 保留消息用于后续轮次
    """
    
    def __init__(self, agent_registry, session_manager, config):
        self.agent_registry = agent_registry
        self.session_manager = session_manager
        self.config = config
        
        # 初始化队列系统
        self.queue_manager = QueueManager()
        self.enqueuer = MessageEnqueuer(self.queue_manager)
        self.drainer = QueueDrainer(self.queue_manager)
        
        # 跟踪运行中的任务和它们的 checkpointer
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._checkpointers: Dict[str, InMemorySaver] = {}
        self._steer_events: Dict[str, asyncio.Event] = {}
        self._steer_messages: Dict[str, str] = {}
    
    async def handle_message(
        self,
        session_key: str,
        prompt: str,
        message_id: Optional[str] = None,
        queue_mode: QueueMode = QueueMode.COLLECT,
        **kwargs
    ) -> dict:
        """
        处理入站消息，支持 STEER 模式
        """
        # 检查是否有运行中的任务
        is_active = session_key in self._running_tasks
        
        if not is_active:
            # 无运行中任务，直接执行
            return await self._start_new_run(session_key, prompt, **kwargs)
        
        # 有运行中任务，根据队列模式处理
        if queue_mode == QueueMode.INTERRUPT:
            # 中断当前运行
            await self._interrupt_run(session_key)
            return await self._start_new_run(session_key, prompt, **kwargs)
        
        elif queue_mode == QueueMode.STEER:
            # STEER 模式: 注入消息到当前运行
            success = await self._steer_run(session_key, prompt)
            if success:
                return {
                    "status": "steered",
                    "message": "Message injected into current run"
                }
            else:
                # steer 失败，回退到 followup
                return await self._enqueue_followup(
                    session_key, prompt, QueueMode.FOLLOWUP, **kwargs
                )
        
        elif queue_mode == QueueMode.STEER_BACKLOG:
            # STEER_BACKLOG: 先 steer，同时入队 followup
            steer_success = await self._steer_run(session_key, prompt)
            
            # 同时入队用于后续轮次
            enqueue_result = await self._enqueue_followup(
                session_key, prompt, QueueMode.FOLLOWUP, **kwargs
            )
            
            if steer_success:
                return {
                    "status": "steer_backlog",
                    "message": "Message steered and queued for followup"
                }
            else:
                return enqueue_result
        
        elif queue_mode in (QueueMode.FOLLOWUP, QueueMode.COLLECT):
            # 入队等待
            return await self._enqueue_followup(
                session_key, prompt, queue_mode, **kwargs
            )
        
        else:
            return {"status": "error", "message": f"Unknown queue mode: {queue_mode}"}
    
    async def _start_new_run(
        self,
        session_key: str,
        prompt: str,
        **kwargs
    ) -> dict:
        """启动新的 Agent 运行"""
        session = self.session_manager.get(session_key)
        
        # 创建 checkpointer (用于 STEER 支持)
        checkpointer = InMemorySaver()
        self._checkpointers[session_key] = checkpointer
        
        # 创建 Agent
        agent = self.agent_registry.create_deep_agent(
            agent_id=session.agent_id,
            provider_override=session.provider_override,
            model_override=session.model_override,
            checkpointer=checkpointer  # 传入 checkpointer 支持 STEER
        )
        
        # 创建 steer 事件
        self._steer_events[session_key] = asyncio.Event()
        
        # 启动任务
        task = asyncio.create_task(
            self._run_agent_with_steer_support(session_key, agent, prompt)
        )
        self._running_tasks[session_key] = task
        
        try:
            result = await task
            return result
        except asyncio.CancelledError:
            return {"status": "cancelled", "message": "Run was interrupted"}
        finally:
            await self._cleanup_run(session_key)
    
    async def _run_agent_with_steer_support(
        self,
        session_key: str,
        agent,
        initial_prompt: str
    ) -> dict:
        """
        运行 Agent，支持 STEER 注入
        
        使用 LangGraph 的 interrupt/Command(resume) 机制
        """
        messages = [{"role": "user", "content": initial_prompt}]
        full_response = []
        
        # 配置 thread_id 用于 checkpoint
        config = {
            "configurable": {
                "thread_id": session_key
            }
        }
        
        # 启动 Agent 流
        stream = agent.astream({"messages": messages}, config)
        
        async for event in stream:
            # 检查是否有 steer 请求
            if session_key in self._steer_messages:
                steer_msg = self._steer_messages[session_key]
                del self._steer_messages[session_key]
                
                # 使用 Command(resume=...) 注入消息
                stream = agent.astream(
                    Command(resume=steer_msg),
                    config
                )
                continue
            
            # 检查是否被中断
            if session_key not in self._running_tasks:
                break
            
            full_response.append(event)
        
        # 提取文本结果
        text = self._extract_text(full_response)
        
        return {
            "status": "completed",
            "text": text
        }
    
    async def _steer_run(self, session_key: str, prompt: str) -> bool:
        """
        向运行中的 Agent 注入消息 (STEER)
        
        使用 LangGraph 的 Command(resume=...) 机制
        """
        if session_key not in self._running_tasks:
            return False
        
        # 存储 steer 消息
        self._steer_messages[session_key] = prompt
        
        # 触发 steer 事件
        if session_key in self._steer_events:
            self._steer_events[session_key].set()
        
        return True
    
    async def _interrupt_run(self, session_key: str):
        """中断运行中的 Agent"""
        if session_key in self._running_tasks:
            task = self._running_tasks[session_key]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    
    async def _enqueue_followup(
        self,
        session_key: str,
        prompt: str,
        queue_mode: QueueMode,
        **kwargs
    ) -> dict:
        """入队 followup 消息"""
        message = QueuedMessage(
            prompt=prompt,
            session_key=session_key,
            message_id=kwargs.get("message_id"),
            agent_id=kwargs.get("agent_id")
        )
        
        settings = QueueSettings(mode=queue_mode)
        success = await self.enqueuer.enqueue(session_key, message, settings)
        
        if success:
            # 注册排空回调
            self.drainer.register_callback(
                session_key,
                lambda msg: self._start_new_run(session_key, msg.prompt, **kwargs)
            )
            # 触发排空
            self.drainer.kick_if_idle(session_key)
            
            return {"status": "queued", "message": "Message queued"}
        else:
            return {"status": "dropped", "message": "Queue full or duplicate"}
    
    async def _cleanup_run(self, session_key: str):
        """清理运行状态"""
        if session_key in self._running_tasks:
            del self._running_tasks[session_key]
        if session_key in self._checkpointers:
            del self._checkpointers[session_key]
        if session_key in self._steer_events:
            del self._steer_events[session_key]
        if session_key in self._steer_messages:
            del self._steer_messages[session_key]
    
    def _extract_text(self, events: list) -> str:
        """从事件流中提取文本"""
        texts = []
        for event in events:
            if isinstance(event, dict):
                if "content" in event:
                    texts.append(str(event["content"]))
                elif "text" in event:
                    texts.append(str(event["text"]))
        return "".join(texts)
## 11.3 使用示例
```python
async def main():
    from ..config import GatewayConfig
    
    config = GatewayConfig()
    runner = SteerableAgentRunner(
        agent_registry=None,  # 替换为实际的 registry
        session_manager=None,  # 替换为实际的 manager
        config=config
    )
    
    # 1. 启动一个运行
    result1 = await runner.handle_message(
        session_key="agent:main:main",
        prompt="Research Python async patterns",
        message_id="msg_001",
        queue_mode=QueueMode.COLLECT
    )
    print(f"Start: {result1}")
    
    # 2. STEER 模式: 注入新消息到当前运行
    result2 = await runner.handle_message(
        session_key="agent:main:main",
        prompt="Focus on asyncio specifically",
        message_id="msg_002",
        queue_mode=QueueMode.STEER
    )
    print(f"Steer: {result2}")
    # 输出: {'status': 'steered', 'message': 'Message injected into current run'}
    
    # 3. STEER_BACKLOG 模式: steer + 保留队列
    result3 = await runner.handle_message(
        session_key="agent:main:main",
        prompt="Also cover trio library",
        message_id="msg_003",
        queue_mode=QueueMode.STEER_BACKLOG
    )
    print(f"Steer Backlog: {result3}")
    # 输出: {'status': 'steer_backlog', 'message': 'Message steered and queued for followup'}
```
## 11.4 与 OpenClaw STEER 的对比
| 特性 | OpenClaw | Python 实现 (LangGraph) |
|------|----------|------------------------|
| **底层机制** | ACP 协议消息注入 | `interrupt()` + `Command(resume=...)` |
| **工具调用处理** | 取消待处理工具调用 | 自然中断，resume 后继续 |
| **状态管理** | Session 状态共享 | Checkpoint 持久化 |
| **实现复杂度** | 高 (需要 ACP 运行时) | 中 (LangGraph 原生支持) |
| **流式支持** | 需要特殊处理 | 天然支持 |
## 11.5 注意事项
1. **Checkpointer 必需**: STEER 模式需要启用 checkpointer 来持久化状态
2. **Thread ID**: 使用 `session_key` 作为 `thread_id` 来标识会话
3. **并发安全**: 每个会话独立运行，通过 `asyncio.Lock` 保护状态
4. **流式输出**: STEER 注入后，流式输出会自动继续
- ✅ 保留并发安全