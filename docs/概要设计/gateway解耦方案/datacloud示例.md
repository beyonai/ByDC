# DataCloud SDK 直接调用方案

> 版本：v1.2 · 日期：2026-04-29

---

## 1. 背景

当前架构中，第三方通过 Gateway 协议（`GatewayCommand` / `ResumeCommand`）与 `DataCloudWorker` 交互，
Worker 负责图构建、流式执行、中断检测与回调。

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
| View/对象解析 | 从 agent_config DB 加载 OWL + 工具 | `OntologyLoader.load_view_with_deps()` 按需解析 |
| 用户身份 | `ByclawDataClarification.user_id` | 由调用方在 `ask()` 中传入 |

### 核心设计决策

1. **Python 直接调用**：第三方 `import` SDK，无 HTTP 层。
2. **流式事件模型**：所有输出（思考过程、中断、最终答案）统一作为异步事件流返回。
   中断不打断流，而是作为 `InterruptEvent` 自然出现在流末尾。
3. **thread_id 外置，历史自动维护**：调用方负责保存 `thread_id`。多轮对话复用同一
   `thread_id`，LangGraph checkpointer 自动存储消息历史，无需调用方手动传入历史记录。
   首次调用传 `None` 由 SDK 内部生成；中断恢复时显式传入已保存的 `thread_id`。
4. **OWL 按需解析**：每次调用时按 `view_codes` / `object_codes` 解析对应 OWL 目录及
   其依赖，不全量加载整个 resource 目录。后续可按需叠加缓存层。
5. **`runner.py` 作为内部基础**：现有 `run_agent()` 是基础层，`OntologyAgent` 在其上
   封装事件转换与中断处理。

---

## 3. 公开 API 设计

### 3.1 客户端接口

```python
class OntologyAgent:
    def __init__(self, config: OntologyAgentConfig) -> None: ...

    def ask(
        self,
        question: str,
        *,
        view_codes: list[str] | None = None,    # 视图编码列表
        object_codes: list[str] | None = None,  # 对象编码列表
        thread_id: str | None = None,           # None = 新会话（SDK 内部生成）
        user_code: str | None = None,           # 用于同义词持久化等用户级功能
        locale: str = "zh_CN",
    ) -> AsyncIterator[OntologyAgentEvent]:
        """发起一次问答，流式返回事件。

        流必须被完整消费。当收到 InterruptEvent 时流自动结束，
        调用方需保存 interrupt.thread_id 并在用户确认后调用 resume()。

        多轮对话：复用同一 thread_id 即可，SDK 通过 checkpointer 自动维护历史，
        无需调用方手动传入历史消息。
        """

    def resume(
        self,
        thread_id: str,
        user_input: str | ParadigmAnswer,
        *,
        view_codes: list[str] | None = None,    # 与 ask() 保持一致
        object_codes: list[str] | None = None,  # 与 ask() 保持一致
        user_code: str | None = None,
    ) -> AsyncIterator[OntologyAgentEvent]:
        """在中断后恢复图执行，继续流式返回事件。

        view_codes / object_codes 须与触发中断的 ask() 调用保持一致，
        初始版本不缓存编译图，resume 时需重新解析 OWL 构建工具。

        user_input:
          - str：简单文本回复（对应 ASK_USER 场景）
          - ParadigmAnswer：用户维度选择（对应 PARADIGM_CLARIFICATION 场景）
        """
```

### 3.2 配置模型

```python
@dataclass
class OntologyAgentConfig:
    api_key: str
    model: str
    resource_path: str | Path   # resource 根目录（含 object/ 和 view/ 子目录）
    base_url: str | None = None
    locale: str = "zh_CN"
    temperature: float = 0.7
```

`resource_path` 在部署时全局配置一次，指向包含 `object/` 和 `view/` 子目录的根目录，
例如：`/data/byclaw-data/resource`。

---

## 4. 事件模型

所有事件继承自 `OntologyAgentEvent`，用 `isinstance` 区分：

```python
class OntologyAgentEvent:
    """所有事件的基类，用于类型注解。"""

# 思考过程（增量 token，LLM 推理中持续发出）
@dataclass
class ThinkingEvent(OntologyAgentEvent):
    content: str

# 执行阶段标题（如"正在查询数据"、"分析结果"）
@dataclass
class StepEvent(OntologyAgentEvent):
    title: str
    detail: str | None = None

# 中断事件（流在此处自动结束，调用方需处理后调用 resume()）
@dataclass
class InterruptEvent(OntologyAgentEvent):
    thread_id: str                              # 调用方必须保存
    reason: str                                 # "PARADIGM_CLARIFICATION" | "ASK_USER" | ...
    prompt: str                                 # 展示给用户的提示语
    paradigm_list: list[ParadigmGroup] | None   # 非空时需展示选择 UI

# 最终答案（增量 token）
@dataclass
class AnswerChunkEvent(OntologyAgentEvent):
    content: str

# 流结束标志（携带完整答案）
@dataclass
class AnswerEvent(OntologyAgentEvent):
    content: str

# 错误（流异常终止）
@dataclass
class ErrorEvent(OntologyAgentEvent):
    message: str
    code: str | None = None
```

### 维度选项模型

```python
@dataclass
class ParadigmOption:
    choice_keyword: str   # 展示给用户的选项文字
    recall: str           # 内部映射值

@dataclass
class ParadigmGroup:
    paradigm_id: str
    paradigm_name: str    # 维度名称，如"部门"
    options: list[ParadigmOption]

@dataclass
class ParadigmAnswer:
    """用户选择的维度答案，传给 resume()。"""
    selections: list[ParadigmGroupSelection]

@dataclass
class ParadigmGroupSelection:
    paradigm_id: str
    paradigm_name: str
    chosen_options: list[ParadigmOption]
```

---

## 5. OWL 按需解析设计

### 5.1 目录结构约定

```
resource/
├── object/
│   ├── by_customer/
│   │   ├── by_customer_definition.owl
│   │   ├── by_customer_mapping.owl
│   │   ├── by_customer_dbsource.owl
│   │   └── by_customer_object_relations.owl
│   └── ...
└── view/
    ├── scene_crm_comprehensive_analysis/
    │   ├── scene_crm_comprehensive_analysis_definition.owl
    │   └── scene_crm_comprehensive_analysis_relations.owl
    └── ...
```

### 5.2 新增方法：`OntologyLoader.load_view_with_deps()`

在 `packages/datacloud-data/src/datacloud_data_sdk/ontology/loader.py` 新增：

```python
def load_view_with_deps(self, resource_path: Path, view_id: str) -> None:
    """按需加载指定 view 及其依赖的 objects，追加到当前 loader（不清空）。

    流程：
    1. 解析 resource/view/{view_id}/ 目录，从 view 定义中读取依赖的 object_codes
    2. 逐一解析 resource/object/{object_code}/ 目录
    3. 使用 load_from_content()（追加语义）写入 self，不影响已有数据
    """
    from datacloud_data_sdk.ontology.owl_parser import OwlParser

    parser = OwlParser()

    # 第一步：解析 view 目录，读取 object_codes
    view_dir = resource_path / "view" / view_id
    parser._parse_new_layout_view_directory(view_dir)

    object_codes: list[str] = []
    if parsed_view := parser._views.get(view_id):
        object_codes = parsed_view.object_codes

    # 第二步：解析依赖的每个 object 目录
    for obj_code in object_codes:
        obj_dir = resource_path / "object" / obj_code
        if obj_dir.is_dir():
            parser._parse_new_layout_object_directory(obj_dir)

    # 第三步：构建内容并追加（不清空现有数据）
    parser._apply_mappings_to_objects()
    self.load_from_content(parser._build_content())
```

### 5.3 配套方法：`OntologyLoader.load_object_with_deps()`

`object_codes` 直接传入时（无 view 包装），需要一个对等方法直接加载 object 目录：

```python
def load_object_with_deps(self, resource_path: Path, object_code: str) -> None:
    """按需加载指定 object，追加到当前 loader（不清空）。"""
    from datacloud_data_sdk.ontology.owl_parser import OwlParser

    parser = OwlParser()
    obj_dir = resource_path / "object" / object_code
    if obj_dir.is_dir():
        parser._parse_new_layout_object_directory(obj_dir)
    parser._apply_mappings_to_objects()
    self.load_from_content(parser._build_content())
```

`OntologyAgent._build_loader()` 内部遍历两个列表：
```python
for view_code in (view_codes or []):
    loader.load_view_with_deps(resource_path, view_code)   # 含依赖 objects
for obj_code in (object_codes or []):
    loader.load_object_with_deps(resource_path, obj_code)  # 直接加载 object
mounted = list(view_codes or []) + list(object_codes or [])
tools = OntologyToolLoader(mounted_objects=mounted, loader=loader).load()
```

### 5.4 为什么用追加而不是清空

`_load_from_owl_content()`（现有的全量加载路径）每次都 `clear()`，不适合按需场景。
`load_from_content()` 是追加语义，多次调用安全叠加，这是按需加载的基础。

### 5.4 每次调用都解析（无缓存，初始版本）

初始版本不加缓存机制，每次 `ask(view_id=...)` 都重新解析 OWL 文件。
后续可在 `OntologyAgent` 层按 `view_id` 缓存 `OntologyLoader` 实例，作为独立优化。

---

## 6. 中断处理流程

### 6.1 正常场景

```
ask(question, view_codes=["scene_sales"], object_codes=["by_customer"])
    │
    ├─ 逐一 load_view_with_deps(resource_path, view_code) → OntologyLoader（追加）
    ├─ 逐一 load_object_with_deps(resource_path, object_code) → OntologyLoader（追加）
    ├─ OntologyToolLoader(mounted_objects=view_codes+object_codes, loader=...).load() → tools
    ├─ build_analysis_graph() + compile
    ├─ astream_events() 流式执行
    │      ├─ on_chat_model_stream → yield ThinkingEvent(chunk)
    │      └─ on_custom_event("step_title") → yield StepEvent(title)
    │
    ├─ 流结束后 aget_state(config)
    │      └─ state.interrupts 为空
    │
    └─ 从 state.values["final_answer"] 提取答案
           └─ yield AnswerEvent(content)
```

### 6.2 中断场景

```
ask(question, view_codes=[...], object_codes=[...])
    │
    ├─ ... (同上执行，直到 user_clarify_node 调用 interrupt())
    │
    ├─ astream_events() 流暂停
    ├─ aget_state(config).interrupts 非空
    │      interrupt.value = {
    │          "reason_code": "PARADIGM_CLARIFICATION",
    │          "ask_user_payload": {"paradigmList": [...], "query": "..."},
    │          "prompt": "查询条件存在歧义，请确认查询维度"
    │      }
    │
    └─ yield InterruptEvent(
               thread_id=thread_id,   ← 调用方保存此值
               reason="PARADIGM_CLARIFICATION",
               prompt="...",
               paradigm_list=[ParadigmGroup(...)]
           )
           ← 流结束，等待用户操作

# 用户在 UI 选择维度后：
resume(thread_id=saved_tid, user_input=ParadigmAnswer(...),
       view_codes=[...], object_codes=[...])  # 与 ask() 保持一致
    │
    ├─ ParadigmAnswer → LangGraph resume_value 格式转换
    │      {"paradigmList": [{"paradigmList": [chosen_items]}]}
    │
    ├─ Command(resume=resume_value)
    ├─ astream_events() 恢复执行
    │      ├─ yield ThinkingEvent(...)
    │      └─ ...
    │
    └─ yield AnswerEvent(content)
```

### 6.3 resume_value 格式转换

`user_clarify_node` 内部期望的格式：
```python
{"paradigmList": [{"paradigmList": [{"choiceKeyword": "华东", "recall": "east_china"}]}]}
```

`OntologyAgent.resume()` 负责将 `ParadigmAnswer` 转换为此格式，调用方无需感知。

### 6.4 user_id 兼容

`user_clarify_node` 原通过 `config["configurable"]["gateway_context"]` 获取 `user_id`
用于同义词持久化。SDK 模式下将 `user_id` 直接写入 `config["configurable"]["user_id"]`，
并在 `user_clarify_node` 中增加兼容读取（约 3 行改动）。未提供 `user_id` 时跳过持久化，
其余逻辑不受影响。

---

## 7. Demo 结构设计

```
examples/chatbi_demo/
├── pyproject.toml          # 依赖：datacloud-analysis（本地路径）
├── README.md
├── demo_normal.py          # 场景一：正常流程（无中断）
└── demo_interrupt.py       # 场景二：中断 + 用户确认 + 恢复
```

---

## 8. 示例代码

### 8.1 场景一：正常流程

```python
# examples/chatbi_demo/demo_normal.py
import asyncio
from datacloud_analysis.ontology_agent import (
    OntologyAgent, OntologyAgentConfig,
    ThinkingEvent, StepEvent, AnswerEvent, ErrorEvent, InterruptEvent,
)

async def main() -> None:
    config = OntologyAgentConfig(
        api_key="sk-xxx",
        model="deepseek-v3",
        base_url="https://api.example.com/v1",
        resource_path="/data/byclaw-data/resource",
    )
    agent = OntologyAgent(config)

    async for event in agent.ask(
        question="各部门本月销售额是多少？",
        view_codes=["scene_sales"],
    ):
        match event:
            case ThinkingEvent(content=c):
                print(c, end="", flush=True)
            case StepEvent(title=t):
                print(f"\n[{t}]")
            case AnswerEvent(content=a):
                print(f"\n\n=== 答案 ===\n{a}")
            case ErrorEvent(message=m):
                print(f"\n[错误] {m}")
            case InterruptEvent():
                print("\n[意外中断]")

asyncio.run(main())
```

### 8.2 场景二：中断 + 恢复

```python
# examples/chatbi_demo/demo_interrupt.py
import asyncio
from collections.abc import AsyncIterator
from datacloud_analysis.ontology_agent import (
    OntologyAgent, OntologyAgentConfig, OntologyAgentEvent,
    ThinkingEvent, StepEvent, AnswerEvent, ErrorEvent, InterruptEvent,
    ParadigmAnswer, ParadigmGroupSelection,
)

async def stream_until_interrupt(
    iterator: AsyncIterator[OntologyAgentEvent],
) -> InterruptEvent | None:
    async for event in iterator:
        match event:
            case ThinkingEvent(content=c):
                print(c, end="", flush=True)
            case StepEvent(title=t):
                print(f"\n[{t}]")
            case AnswerEvent(content=a):
                print(f"\n\n=== 答案 ===\n{a}")
            case ErrorEvent(message=m):
                print(f"\n[错误] {m}")
            case InterruptEvent() as ie:
                return ie
    return None


def mock_user_select(event: InterruptEvent) -> ParadigmAnswer:
    """模拟用户在 UI 选择维度（真实场景由前端完成）。"""
    print(f"\n[需要澄清] {event.prompt}")
    selections = []
    for group in (event.paradigm_list or []):
        print(f"  维度「{group.paradigm_name}」→ 自动选第一项：{group.options[0].choice_keyword}")
        selections.append(
            ParadigmGroupSelection(
                paradigm_id=group.paradigm_id,
                paradigm_name=group.paradigm_name,
                chosen_options=group.options[:1],
            )
        )
    return ParadigmAnswer(selections=selections)


async def main() -> None:
    config = OntologyAgentConfig(
        api_key="sk-xxx",
        model="deepseek-v3",
        base_url="https://api.example.com/v1",
        resource_path="/data/byclaw-data/resource",
    )
    agent = OntologyAgent(config)

    view_codes = ["scene_sales"]

    # 第一轮：发起问题
    print("问：华东区域的销售额是多少？\n")
    interrupt_event = await stream_until_interrupt(
        agent.ask(
            question="华东区域的销售额是多少？",
            view_codes=view_codes,
            user_code="user_001",
        )
    )
    if interrupt_event is None:
        return

    # 用户选择
    saved_thread_id = interrupt_event.thread_id
    user_answer = mock_user_select(interrupt_event)

    # 第二轮：恢复（view_codes 与 ask() 保持一致）
    print("\n[继续执行...]\n")
    await stream_until_interrupt(
        agent.resume(
            thread_id=saved_thread_id,
            user_input=user_answer,
            view_codes=view_codes,
            user_code="user_001",
        )
    )

asyncio.run(main())
```

---

## 9. 内部实现关键点

### 9.1 OntologyAgent 内部结构

```
OntologyAgent
├── _config: OntologyAgentConfig
│
├── _build_loader(view_id) → OntologyLoader
│       ├─ loader = OntologyLoader()
│       ├─ loader.load_view_with_deps(resource_path, view_id)
│       ├─ inject_virtual_actions(loader)
│       └─ configure_loader(loader, model, api_key, ...)
│
├── _iter_events(compiled, input_payload, run_config) → AsyncIterator[OntologyAgentEvent]
│       ├─ astream_events(version="v2") 消费原始事件
│       ├─ on_chat_model_stream → yield ThinkingEvent(chunk)
│       ├─ 流结束后 aget_state() 检查 interrupts
│       ├─ interrupts 非空 → yield InterruptEvent，结束
│       └─ interrupts 为空 → yield AnswerChunkEvent* + AnswerEvent，结束
│
├── ask()    → _build_loader → build_graph → _iter_events
└── resume() → Command(resume=...) → _iter_events
```

### 9.2 与 runner.py 的关系

`runner.py` 使用 `stream_mode="values"`（完整状态快照），适合批处理。
`OntologyAgent` 内部改用 `astream_events(version="v2")`，拿增量 LLM token，
实现真正的流式思考过程。两者并行存在，分别服务不同场景。

---

## 10. 待实现清单

| 编号 | 内容 | 位置 |
|------|------|------|
| T1 | `OntologyLoader.load_view_with_deps()` + `load_object_with_deps()` | `packages/datacloud-data/.../loader.py` |
| T2 | `user_clarify_node` 兼容直接读 `user_id`（约 3 行） | `packages/datacloud-analysis/.../user_clarify_node.py` |
| T3 | `OntologyAgent` + 事件模型 + `ParadigmAnswer` 转换 | `packages/datacloud-analysis/src/datacloud_analysis/ontology_agent.py`（新建）<br>+ `__init__.py` 追加导出 |
| T4 | Demo 脚本 | `examples/chatbi_demo/` |
| T5 | `worker.py` 重构：动态路径改用 `OntologyAgent` 驱动 | `byclaw-data/src/byclaw_data/worker.py` |

---

## 11. worker.py 重构架构

### 11.1 现状与目标

**现状**：`worker.py` 中 `DataCloudWorker` 直接持有图构建、OWL 加载、流式事件处理、中断检测的全部逻辑。
**目标**：`OntologyAgent` 成为**唯一的核心引擎**，`worker.py` 退化为薄协议适配层。

```
# 现状
Gateway ──→ DataCloudWorker（图构建 + 流式 + 中断 + OWL 全耦合）

# 目标
Gateway ──→ DataCloudWorker（协议解析 + 生命周期）
                   │
                   └──→ OntologyAgent（图构建 + 流式 + 中断 + OWL）
                              ↑
                   第三方也直接调用 OntologyAgent
```

### 11.2 worker.py 中的两条路径

当前 `DataCloudWorker.process_command` 内部存在**两条互斥路径**：

| 维度 | 静态路径（现有） | 动态路径（`_is_dynamic_agent`） |
|------|-----------------|-------------------------------|
| 触发条件 | `extra_payload.agent_id` 匹配 `plugin_registry.agent_configs` | `extra_payload.call_object_ids` 或 `call_view_ids` 非空 |
| Graph 配置来源 | `AgentConfig`：`prompts_dict`、`tools_dict`、`loader`、`skip_action_families` | `_dyn_object_ids + _dyn_view_ids` 直接组装 `mounted_objects` |
| OWL 加载 | AgentConfig 的 `extra["loader"]`（全量预加载） | `self._extract_shared_loader()`（取第一个 loader，无 OWL 选择） |
| Graph 缓存 key | `{agent_id}:{conf_hash}` | `dynamic:{sha1[:12]}` |
| 重构优先级 | **Phase 2**（需扩展 OntologyAgent 支持 prompts/tools 注入） | **Phase 1**（直接替换，OntologyAgent 已具备能力） |

### 11.3 Phase 1：动态路径重构

**改动范围**：仅 `_is_dynamic_agent == True` 时的分支（约 40 行）。

```python
# 重构后的动态路径（伪代码）
if _is_dynamic_agent:
    agent = OntologyAgent(
        OntologyAgentConfig(
            api_key=self.api_key,
            model=self.model_name,
            base_url=self.base_url,
            resource_path=self._resource_path,   # 新增配置项
        )
    )
    view_codes = _dyn_view_ids
    object_codes = _dyn_object_ids
    thread_id = self._build_thread_id(session_id=context.session_id, agent_key=runtime_agent_key)

    if isinstance(command, ResumeCommand) or _paradigm_resume_value is not None:
        resume_input = _to_paradigm_answer(_paradigm_resume_value or command.reply_data)
        event_iter = agent.resume(thread_id, resume_input,
                                  view_codes=view_codes, object_codes=object_codes)
    else:
        event_iter = agent.ask(question=latest_user_text,
                               view_codes=view_codes, object_codes=object_codes,
                               thread_id=thread_id,
                               user_code=_extract_user_code(context))

    async for event in event_iter:
        await _translate_event_to_gateway(event, context)

    return stream_result
```

**`_translate_event_to_gateway`** 负责将 `OntologyAgentEvent` 映射为 Gateway SSE：

| OntologyAgentEvent | Gateway 操作 |
|--------------------|-------------|
| `ThinkingEvent` | `context.emit_chunk(..., REASONING_LOG_START, think_text)` |
| `StepEvent` | `context.emit_chunk(..., REASONING_LOG_START, think_text)`（或 `sub_step`） |
| `AnswerChunkEvent` | `context.emit_chunk(..., ANSWER_DELTA, text)` |
| `AnswerEvent` | `context.flush_to_history()` → `return {"status": "done"}` |
| `InterruptEvent(reason="PARADIGM_CLARIFICATION")` | `context.complex_ask_user(AskUserEvent(...))` → `return {"status": "waiting"}` |
| `InterruptEvent(其他)` | `context.ask_user(AskUserEvent(...))` → `return {"status": "waiting"}` |
| `ErrorEvent` | `logger.error(...)` → 向用户 emit 错误内容 |

### 11.4 Phase 2：静态路径重构（规划）

静态路径依赖 `AgentConfig` 中的 `prompts_dict`、`tools_dict`、`skip_action_families`，
需要在 `OntologyAgentConfig` 或 `OntologyAgent.ask()` 中扩展对应参数后才能迁移。

暂时**保留现有静态路径不变**，等 Phase 1 稳定后再规划 Phase 2。

### 11.5 保留在 worker.py 的职责

重构后 `worker.py` 继续负责以下与 Gateway 协议强绑定的逻辑，**不迁入 `OntologyAgent`**：

- **协议解析**：`GatewayCommand` / `ResumeCommand` → question / view_codes / object_codes / thread_id
- **Agent config 加载**：动态从 `plugin_registry` 加载 `AgentConfig`
- **Resume 幂等去重**：`_resume_result_cache` + `_resume_inflight`
- **闲聊检测**：`_is_light_chitchat()` 快速回复
- **推荐问题任务**：`reco_plugin.generate_recommended_questions()` 后台并发
- **心跳保活**：`_heartbeat_loop()`
- **Graph 缓存管理**：静态路径的 LRU `self.graphs`（动态路径迁 OntologyAgent 后无需此缓存）
