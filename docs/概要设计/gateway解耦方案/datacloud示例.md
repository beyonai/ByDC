# DataCloud SDK 直接调用方案

> 版本：v1.0 · 日期：2026-04-29

---

## 1. 背景

当前架构中，第三方通过 Gateway 协议（`GatewayCommand` / `ResumeCommand`）与 `DataCloudWorker` 交互，Worker 负责图构建、流式执行、中断检测与回调。

本方案目标：**第三方直接调用 `by-datacloud` SDK，无需 Gateway 中间层。**

---

## 2. 整体思路

### 与 worker.py 的职责拆分

| 职责 | Gateway 模式（worker.py） | SDK 直调模式 |
|------|--------------------------|-------------|
| 协议转换 | GatewayCommand → graph input | 不需要 |
| 图构建 | `_build_graph(tools, prompts, ontology)` | 同，内部封装 |
| 流式执行 | `_stream_graph()` → astream_events | 同，内部封装 |
| 中断检测 | 读 `snapshot.interrupts` → 回调 `context.ask_user()` | 读 `snapshot.interrupts` → 作为流事件返回 |
| 中断恢复 | `Command(resume=paradigm_input)` | 同，由 `resume()` 方法传入 |
| View/对象解析 | 从 agent_config DB 加载 OWL+工具 | 通过 `ViewRegistry` 接口，第三方实现 |
| 用户身份 | `ByclawDataClarification.user_id` | 由调用方在 `ask()` 中传入 |

### 核心设计决策

1. **流式事件模型**：所有输出（思考过程、中断、最终答案）统一作为异步事件流返回，中断不打断流，而是作为 `InterruptEvent` 自然出现在流末尾。
2. **thread_id 外置**：调用方负责保存 `thread_id`。首次调用由 SDK 生成并在 `InterruptEvent` 中返回，恢复时显式传入。
3. **ViewRegistry 接口**：SDK 定义 `ViewRegistry` 抽象，调用方实现 ID → 配置的映射，SDK 不绑定任何数据库或服务。
4. **runner.py 作为内部基础**：现有 `run_agent()` 是基础层，`ChatBIClient` 在其上封装事件转换与中断处理。

---

## 3. 公开 API 设计

### 3.1 客户端接口

```python
class ChatBIClient:
    def __init__(
        self,
        config: ChatBIConfig,
        view_registry: ViewRegistry | None = None,
    ) -> None: ...

    def ask(
        self,
        question: str,
        *,
        view_id: str | None = None,
        object_id: str | None = None,
        thread_id: str | None = None,   # None = 新会话（SDK 内部生成）
        user_id: str | None = None,     # 用于同义词持久化等用户级功能
        locale: str = "zh_CN",
    ) -> AsyncIterator[ChatBIEvent]:
        """发起一次问答，流式返回事件。

        流必须被完整消费。当收到 InterruptEvent 时流自动结束，
        调用方需保存 interrupt.thread_id 并在用户确认后调用 resume()。
        """

    def resume(
        self,
        thread_id: str,
        user_input: str | ParadigmAnswer,
    ) -> AsyncIterator[ChatBIEvent]:
        """在中断后恢复图执行，继续流式返回事件。

        user_input:
          - str：简单文本回复（对应 ASK_USER 场景）
          - ParadigmAnswer：用户维度选择（对应 PARADIGM_CLARIFICATION 场景）
        """
```

### 3.2 配置模型

```python
@dataclass
class ChatBIConfig:
    api_key: str
    model: str
    base_url: str | None = None
    locale: str = "zh_CN"
    temperature: float = 0.7
```

### 3.3 ViewRegistry 接口（调用方实现）

```python
class ViewConfig(TypedDict):
    tools: list[dict[str, Any]]           # 工具定义列表
    prompts_overwrite: dict[str, str]     # 系统提示覆盖（可为空）
    mounted_objects: list[Any]            # OWL 本体对象（可为空）

class ViewRegistry(Protocol):
    def resolve(self, view_id: str) -> ViewConfig:
        """根据 view_id 或 object_id 返回视图配置。"""
        ...
```

**为什么这样设计**：SDK 只负责推理，视图配置（数据源、schema、工具）属于业务层知识，由调用方掌握。SDK 不绑定任何配置数据库，第三方可用文件、DB、内存任意方式实现。

---

## 4. 事件模型

所有事件继承自 `ChatBIEvent`（sealed union，用 `isinstance` 区分）：

```python
# 思考过程（增量 token，LLM 推理中持续发出）
@dataclass
class ThinkingEvent(ChatBIEvent):
    content: str            # 增量文本

# 执行阶段标题（如"正在查询数据"、"分析结果"）
@dataclass
class StepEvent(ChatBIEvent):
    title: str
    detail: str | None = None

# 中断事件（流在此处自动结束）
@dataclass
class InterruptEvent(ChatBIEvent):
    thread_id: str                          # 调用方必须保存，用于 resume()
    reason: str                             # "PARADIGM_CLARIFICATION" | "ASK_USER" | ...
    prompt: str                             # 展示给用户的提示语
    paradigm_list: list[ParadigmGroup] | None  # 维度选项，非空时需展示选择 UI

# 最终答案（增量 token）
@dataclass
class AnswerChunkEvent(ChatBIEvent):
    content: str

# 流结束标志（携带完整答案）
@dataclass
class AnswerEvent(ChatBIEvent):
    content: str

# 错误（流异常终止）
@dataclass
class ErrorEvent(ChatBIEvent):
    message: str
    code: str | None = None
```

### 维度选项模型

```python
@dataclass
class ParadigmOption:
    choice_keyword: str     # 展示给用户的选项文字
    recall: str             # 内部映射值

@dataclass
class ParadigmGroup:
    paradigm_id: str
    paradigm_name: str      # 维度名称，如"部门"
    options: list[ParadigmOption]

@dataclass
class ParadigmAnswer:
    """用户选择的维度答案，传给 resume()。"""
    selections: list[ParadigmGroupSelection]

@dataclass
class ParadigmGroupSelection:
    paradigm_id: str
    paradigm_name: str
    chosen_options: list[ParadigmOption]    # 用户选中的项
```

---

## 5. 中断处理流程

### 5.1 正常场景

```
ask(question, view_id)
    │
    ├─ resolve view_id → ViewConfig
    ├─ build_analysis_graph() + compile (可缓存)
    ├─ astream_events() 流式执行
    │      ├─ on_chat_model_stream → yield ThinkingEvent(chunk)
    │      └─ on_custom_event("step_title") → yield StepEvent(title)
    │
    ├─ 流结束后 aget_state(config)
    │      └─ state.interrupts 为空
    │
    └─ 从 state.values["final_answer"] 提取答案
           └─ yield AnswerEvent(content)  ← 流结束
```

### 5.2 中断场景

```
ask(question, view_id)
    │
    ├─ ... (同上执行，直到 user_clarify_node 调用 interrupt())
    │
    ├─ astream_events() 流暂停
    │
    ├─ aget_state(config).interrupts 非空
    │      └─ interrupt.value = {
    │              "reason_code": "PARADIGM_CLARIFICATION",
    │              "ask_user_payload": {"paradigmList": [...], "query": "..."},
    │              "prompt": "查询条件存在歧义，请确认查询维度"
    │         }
    │
    └─ yield InterruptEvent(
               thread_id=thread_id,   ← 调用方保存此值
               reason="PARADIGM_CLARIFICATION",
               prompt="...",
               paradigm_list=[ParadigmGroup(...)]
           )
           ← 流结束，等待用户操作

# 用户在 UI 上选择维度后：
resume(thread_id=saved_tid, user_input=ParadigmAnswer(...))
    │
    ├─ 将 ParadigmAnswer → LangGraph resume_value 格式转换
    │      resume_value = {"paradigmList": [{"paradigmList": [chosen_items]}]}
    │
    ├─ Command(resume=resume_value)
    ├─ astream_events() 恢复执行
    │      ├─ yield ThinkingEvent(...)
    │      └─ ...
    │
    └─ yield AnswerEvent(content)
```

### 5.3 中断内部机制说明

`user_clarify_node` 内部在 `interrupt()` 返回（resume 时）会自动执行：
- `_format_clarification()` — 将用户选择格式化为工具参数
- `normalize_clarification_params()` — 归一化参数
- `persist_confirmed_synonyms()` — 持久化同义词（需要 `user_id`，可选）

SDK 通过在 `run_config["configurable"]["user_id"]` 传入调用方提供的 `user_id` 来支持同义词持久化。若未提供，跳过持久化，其余逻辑不受影响。

---

## 6. Demo 结构设计

```
examples/chatbi_demo/
├── pyproject.toml              # 依赖：by-datacloud（本地路径）
├── README.md
│
├── mock_registry/              # ViewRegistry 的 mock 实现（演示用）
│   ├── __init__.py
│   ├── registry.py             # FileViewRegistry: 从 YAML 加载 view 配置
│   └── views/
│       └── sales_view.yaml     # 示例视图配置（工具、数据源、提示词）
│
├── demo_normal.py              # 场景一：正常流程（无中断）
└── demo_interrupt.py           # 场景二：中断 + 用户确认 + 恢复
```

---

## 7. 示例代码

### 7.1 场景一：正常流程

```python
# examples/chatbi_demo/demo_normal.py
"""正常场景：问题 + view_id → 流式思考过程 + 最终答案"""

import asyncio
from datacloud_analysis.client import (
    ChatBIClient,
    ChatBIConfig,
    ThinkingEvent,
    StepEvent,
    AnswerEvent,
    ErrorEvent,
    InterruptEvent,
)
from mock_registry.registry import FileViewRegistry


async def main() -> None:
    config = ChatBIConfig(
        api_key="sk-xxx",
        model="deepseek-v3",
        base_url="https://api.example.com/v1",
    )
    registry = FileViewRegistry("mock_registry/views")
    client = ChatBIClient(config, view_registry=registry)

    question = "各部门本月销售额是多少？"
    view_id = "sales_view"

    async for event in client.ask(question=question, view_id=view_id):
        match event:
            case ThinkingEvent(content=c):
                print(c, end="", flush=True)
            case StepEvent(title=t):
                print(f"\n[{t}]")
            case AnswerEvent(content=a):
                print(f"\n\n=== 最终答案 ===\n{a}")
            case ErrorEvent(message=m):
                print(f"\n[错误] {m}")
            case InterruptEvent():
                # 正常场景不应出现，防御性处理
                print("\n[意外中断]")


asyncio.run(main())
```

### 7.2 场景二：中断 + 恢复

```python
# examples/chatbi_demo/demo_interrupt.py
"""中断场景：SDK 返回 InterruptEvent → 用户选择维度 → resume() 继续"""

import asyncio
from datacloud_analysis.client import (
    ChatBIClient,
    ChatBIConfig,
    ThinkingEvent,
    StepEvent,
    AnswerEvent,
    ErrorEvent,
    InterruptEvent,
    ParadigmAnswer,
    ParadigmGroupSelection,
)
from mock_registry.registry import FileViewRegistry


def _mock_user_select(event: InterruptEvent) -> ParadigmAnswer:
    """模拟用户在 UI 上选择维度（真实场景由前端交互完成）。"""
    print(f"\n[需要澄清] {event.prompt}")
    selections = []
    for group in (event.paradigm_list or []):
        print(f"  维度「{group.paradigm_name}」选项：")
        for i, opt in enumerate(group.options):
            print(f"    {i}. {opt.choice_keyword}")
        # 自动选第一个（demo 用）
        chosen = group.options[:1]
        print(f"  → 选择：{chosen[0].choice_keyword}")
        selections.append(
            ParadigmGroupSelection(
                paradigm_id=group.paradigm_id,
                paradigm_name=group.paradigm_name,
                chosen_options=chosen,
            )
        )
    return ParadigmAnswer(selections=selections)


async def stream_events(client: ChatBIClient, iterator: any) -> InterruptEvent | None:
    """消费事件流，遇到 InterruptEvent 时返回它。"""
    async for event in iterator:
        match event:
            case ThinkingEvent(content=c):
                print(c, end="", flush=True)
            case StepEvent(title=t):
                print(f"\n[{t}]")
            case AnswerEvent(content=a):
                print(f"\n\n=== 最终答案 ===\n{a}")
            case ErrorEvent(message=m):
                print(f"\n[错误] {m}")
            case InterruptEvent() as ie:
                return ie
    return None


async def main() -> None:
    config = ChatBIConfig(
        api_key="sk-xxx",
        model="deepseek-v3",
        base_url="https://api.example.com/v1",
    )
    registry = FileViewRegistry("mock_registry/views")
    client = ChatBIClient(config, view_registry=registry)

    question = "华东区域的销售额是多少？"  # 「华东」存在维度歧义，会触发中断
    view_id = "sales_view"

    # ── 第一轮：发起问题 ──────────────────────────────
    print(f"问：{question}\n")
    interrupt_event = await stream_events(client, client.ask(question=question, view_id=view_id))

    if interrupt_event is None:
        return  # 无中断，正常结束

    # ── 中断：用户选择 ──────────────────────────────
    saved_thread_id = interrupt_event.thread_id  # 调用方必须保存
    user_answer = _mock_user_select(interrupt_event)

    # ── 第二轮：恢复执行 ──────────────────────────────
    print("\n[继续执行...]\n")
    await stream_events(client, client.resume(thread_id=saved_thread_id, user_input=user_answer))


asyncio.run(main())
```

---

## 8. 内部实现关键点

### 8.1 ChatBIClient 内部结构

```
ChatBIClient
├── _graph_cache: dict[str, CompiledGraph]  # view_id → 编译图（避免重复编译）
├── _config: ChatBIConfig
├── _view_registry: ViewRegistry | None
│
├── _resolve_view(view_id) → ViewConfig
├── _get_or_build_graph(view_id) → CompiledGraph
├── _make_run_config(thread_id, user_id, locale) → dict
├── _iter_events(compiled, input_payload, run_config) → AsyncIterator[ChatBIEvent]
│       ├─ astream_events() 消费原始事件
│       ├─ 转换 on_chat_model_stream → ThinkingEvent
│       ├─ 流结束后 aget_state() 检查 interrupts
│       ├─ interrupts 非空 → yield InterruptEvent，结束
│       └─ interrupts 为空 → yield AnswerChunkEvent* + AnswerEvent，结束
│
├── ask() → 调用 _get_or_build_graph + _iter_events
└── resume() → 用 Command(resume=...) 调用 _iter_events
```

### 8.2 与 runner.py 的关系

`runner.py` 中的 `run_agent()` 使用 `stream_mode="values"`（返回完整状态快照），适合批处理场景。

`ChatBIClient` 内部改用 `astream_events(version="v2")`，可以拿到增量 LLM token（`on_chat_model_stream` 事件），才能实现真正的流式思考过程展示。两者并不冲突，分别服务不同场景。

### 8.3 resume_value 格式转换

`user_clarify_node` 期望的内部格式：
```python
{"paradigmList": [{"paradigmList": [{"choiceKeyword": "华东", "recall": "east_china"}]}]}
```

`ChatBIClient.resume()` 负责将 `ParadigmAnswer` 转换为上述格式，调用方无需感知内部结构。

### 8.4 gateway_context 的替代

原 `user_clarify_node` 通过 `config["configurable"]["gateway_context"]` 获取 `user_id` 用于同义词持久化。

SDK 模式下，将 `user_id` 直接注入 `config["configurable"]["user_id"]`，并在 `user_clarify_node` 中兼容两种来源：优先读 `gateway_context`，回退到直接的 `user_id` key。这是对现有代码的最小修改。

---

## 9. 待确认问题

| 问题 | 说明 |
|------|------|
| graph 缓存粒度 | 当前方案按 `view_id` 缓存编译图。若 `ViewConfig` 会动态变化（如工具配置热更新），缓存需加版本号或 TTL |
| 多轮对话 | 同一 `thread_id` 可连续调用 `ask()`（不经过中断），LangGraph checkpoint 自动维护上下文。Demo 目前只展示单轮，是否需要演示多轮？ |
| `ViewRegistry` 实现位置 | mock 实现放在 `examples/chatbi_demo/`；若有真实项目需要，可提升到独立包 |
| `user_clarify_node` 修改 | 需在现有代码中添加 `user_id` 直接读取兜底（约 3 行改动）。是否现在做？ |
