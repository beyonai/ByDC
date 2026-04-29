# dataCloud 的 worker 重构方案

> 版本：v1.3 · 日期：2026-04-29

---

## 背景

当前架构中，第三方通过 Gateway 协议（`GatewayCommand` / `ResumeCommand`）与 `DataCloudWorker` 交互，
Worker 负责图构建、流式执行、中断检测与回调。

本方案目标：

1. **对外**：提取 `OntologyAgent` 作为公开 Python SDK，第三方可直接 `import` 调用，无需 Gateway 中间层。
2. **对内**：`DataCloudWorker` 改用 `OntologyAgent` 作为内部引擎，消除双重实现，统一维护路径。

---

## 现状分析

### 当前架构

```
Gateway ──→ DataCloudWorker
                │
                ├─ 图构建（create_agent / _build_graph）
                ├─ OWL 加载（全量预加载或 shared_loader）
                ├─ astream_events 流式执行
                ├─ aget_state 中断检测
                └─ context.ask_user / complex_ask_user 回调
```

所有核心能力都耦合在 `DataCloudWorker` 内部，第三方无法脱离 Gateway 直接复用。

### worker.py 两条路径

`DataCloudWorker.process_command` 内部存在两条互斥执行路径：

| 维度 | 静态路径 | 动态路径（`_is_dynamic_agent`） |
|------|---------|-------------------------------|
| 触发条件 | `extra_payload.agent_id` 匹配 `plugin_registry.agent_configs` | `extra_payload.call_object_ids` 或 `call_view_ids` 非空 |
| 配置来源 | `AgentConfig`：prompts、tools、loader、skip_action_families | 直接从请求提取 `object_codes` / `view_codes` |
| OWL 加载 | AgentConfig 的 `extra["loader"]`（全量预加载） | `_extract_shared_loader()`（共用全量 loader） |
| Graph 缓存 key | `{agent_id}:{conf_hash}` | `dynamic:{sha1[:12]}` |

### Gateway 模式与 SDK 直调模式的职责对比

| 职责 | Gateway 模式（worker.py） | SDK 直调模式 |
|------|--------------------------|-------------|
| 协议转换 | GatewayCommand → graph input | 不需要 |
| 图构建 | `_build_graph(tools, prompts, ontology)` | 同，内部封装 |
| 流式执行 | `_stream_graph()` → astream_events | 同，内部封装 |
| 中断检测 | 读 `snapshot.interrupts` → 回调 `context.ask_user()` | 读 `snapshot.interrupts` → 作为流事件返回 |
| 中断恢复 | `Command(resume=paradigm_input)` | 同，由 `resume()` 方法传入 |
| OWL 解析 | 全量预加载，从 agent_config DB 加载 | `OntologyLoader.load_view_with_deps()` 按需解析 |
| 用户身份 | `ByclawDataClarification.user_id` | 由调用方在 `ask()` 中传入 `user_code` |

---

## 概要设计

### 核心设计决策

1. **Python 直接调用**：第三方 `import` SDK，无 HTTP 层。
2. **流式事件模型**：所有输出（思考过程、中断、最终答案）统一作为异步事件流返回。
   中断不打断流，而是作为 `InterruptEvent` 自然出现在流末尾。
3. **thread_id 由调用方管理**：
   - **多轮对话**：调用方自行生成并持久化 `thread_id`（如 `str(uuid.uuid4())`），每轮 `ask()` 传入相同值；LangGraph checkpointer 自动存储消息历史，无需手动传入历史记录。
   - **一次性问答**：传 `thread_id=None`，SDK 内部生成，调用方无需保存。
   - **中断恢复**：调用方用发起 `ask()` 时的同一个 `thread_id` 调用 `resume()`。
4. **OWL 按需解析**：每次调用时按 `view_codes` / `object_codes` 解析对应 OWL 目录及
   其依赖，不全量加载整个 resource 目录。后续可按需叠加缓存层。
5. **`OntologyAgent` 作为统一引擎**：现有 `runner.py` 是基础层；`OntologyAgent` 在其上
   封装事件转换与中断处理，并同时服务 Gateway 内部路径与第三方直调路径。

### 目标架构

```
# 重构后
Gateway ──→ DataCloudWorker（协议解析 + 生命周期管理）
                   │
                   └──→ OntologyAgent（图构建 + 流式 + 中断 + OWL）
                              ↑
                   第三方也直接调用 OntologyAgent
```

### 分阶段迁移计划

| 阶段 | 范围 | 依赖 | 说明 |
|------|------|------|------|
| Phase 1 | worker.py 动态路径改用 `OntologyAgent` | T3 完成 | 动态路径已是 view_codes/object_codes 模式，直接替换 |
| Phase 2 | worker.py 静态路径改用 `OntologyAgent` | Phase 1 稳定 | 需扩展 `OntologyAgentConfig` 支持 prompts/tools 注入 |

### 待实现清单

| 编号 | 内容 | 位置 |
|------|------|------|
| T1 | `OntologyLoader.load_view_with_deps()` + `load_object_with_deps()` | `packages/datacloud-data/.../loader.py` |
| T2 | `user_clarify_node` 兼容直接读 `user_code`（约 3 行） | `packages/datacloud-analysis/.../user_clarify_node.py` |
| T3 | `OntologyAgent` + 事件模型 + `ParadigmAnswer` 转换 | `packages/datacloud-analysis/src/datacloud_analysis/ontology_agent.py`（新建）<br>+ `__init__.py` 追加导出 |
| T4 | Demo 脚本 | `examples/chatbi_demo/` |
| T5 | `worker.py` 动态路径重构：改用 `OntologyAgent` 驱动 | `byclaw-data/src/byclaw_data/worker.py` |
| T6 | `OntologyAgent` 进程级图缓存：按 `(view_codes, object_codes)` 缓存编译图和 OntologyLoader，消除动态路径每次重建的开销 | `packages/datacloud-analysis/src/datacloud_analysis/ontology_agent.py` |

---

## 详细设计

### 1. OntologyAgent 公开 API

**文件位置**：`packages/datacloud-analysis/src/datacloud_analysis/ontology_agent.py`

#### 1.1 客户端接口

`ask()` 和 `resume()` 均为**异步生成器方法**（`async def` + `yield`），可直接用 `async for` 消费。

```python
class OntologyAgent:
    def __init__(self, config: OntologyAgentConfig) -> None: ...

    async def ask(
        self,
        question: str,
        *,
        view_codes: list[str] | None = None,    # 视图编码列表
        object_codes: list[str] | None = None,  # 对象编码列表
        thread_id: str | None = None,           # 多轮对话由调用方传入并保存；None = 一次性问答
        user_code: str | None = None,           # 用于同义词持久化等用户级功能
        locale: str = "zh_CN",                  # 覆盖 OntologyAgentConfig 中的默认 locale
    ) -> AsyncGenerator[OntologyAgentEvent, None]:
        """发起一次问答，流式返回事件。

        thread_id 使用规则：
          - 多轮对话：调用方自行生成（如 str(uuid.uuid4())）并在每轮 ask() 中传入相同值。
            LangGraph checkpointer 自动维护历史，无需手动传入历史消息。
          - 一次性问答：传 None，SDK 内部生成，调用方无需保存。
          - 中断恢复：resume() 使用与本次 ask() 相同的 thread_id。

        流必须被完整消费。收到 InterruptEvent 时流自动结束，调用方需调用 resume() 恢复。
        """

    async def resume(
        self,
        thread_id: str,
        user_input: str | ParadigmAnswer,
        *,
        view_codes: list[str] | None = None,    # 与触发中断的 ask() 保持一致
        object_codes: list[str] | None = None,  # 与触发中断的 ask() 保持一致
        user_code: str | None = None,
    ) -> AsyncGenerator[OntologyAgentEvent, None]:
        """在中断后恢复图执行，继续流式返回事件。

        view_codes / object_codes 须与触发中断的 ask() 调用保持一致。

        user_input:
          - str：简单文本回复（对应 ASK_USER 场景）
          - ParadigmAnswer：用户维度选择（对应 PARADIGM_CLARIFICATION 场景）
        """
```

#### 1.2 配置模型

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

### 2. 事件模型

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
    thread_id: str                                    # 与 ask() 传入的 thread_id 一致，方便调用方核对
    reason: str                                       # "PARADIGM_CLARIFICATION" | "ASK_USER" | ...
    prompt: str                                       # 展示给用户的提示语
    paradigm_list: list[ParadigmGroup] | None = None  # 非空时需展示选择 UI（PARADIGM_CLARIFICATION 场景）

# 最终答案（完整内容，一次性 yield，初始版本不做增量推送）
@dataclass
class AnswerEvent(OntologyAgentEvent):
    content: str

# 错误（流异常终止）
@dataclass
class ErrorEvent(OntologyAgentEvent):
    message: str
    code: str | None = None
```

> **关于答案推送**：初始版本在 `astream_events` 结束后从 `state.values["final_answer"]`
> 提取完整答案，一次性 yield `AnswerEvent`，不做增量推送。`AnswerChunkEvent` 作为
> 预留类型，待后续 `respond` 节点支持流式输出时启用。

#### 维度选项模型

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

### 3. OWL 按需解析

#### 3.1 resource 目录结构约定

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

#### 3.2 新增方法：`OntologyLoader.load_view_with_deps()`

在 `packages/datacloud-data/src/datacloud_data_sdk/ontology/loader.py` 新增：

```python
def load_view_with_deps(self, resource_path: Path, view_id: str) -> None:
    """按需加载指定 view 及其依赖的 objects，追加到当前 loader（不清空）。"""
    from datacloud_data_sdk.ontology.owl_parser import OwlParser

    parser = OwlParser()

    view_dir = resource_path / "view" / view_id
    if view_dir.is_dir():
        parser._parse_new_layout_view_directory(view_dir)

    object_codes: list[str] = []
    if parsed_view := parser._views.get(view_id):
        object_codes = parsed_view.object_codes

    for obj_code in object_codes:
        obj_dir = resource_path / "object" / obj_code
        if obj_dir.is_dir():
            parser._parse_new_layout_object_directory(obj_dir)

    parser._apply_mappings_to_objects()
    self.load_from_content(parser._build_content())
```

#### 3.3 配套方法：`OntologyLoader.load_object_with_deps()`

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

#### 3.4 `OntologyAgent._build_loader()` 完整调用序列

```python
def _build_loader(
    self,
    view_codes: list[str] | None,
    object_codes: list[str] | None,
) -> tuple[OntologyLoader, list[str]]:
    resource_path = Path(self._config.resource_path)
    loader = OntologyLoader()

    for view_code in (view_codes or []):
        loader.load_view_with_deps(resource_path, view_code)
    for obj_code in (object_codes or []):
        loader.load_object_with_deps(resource_path, obj_code)

    # 注入虚拟动作、配置 LLM（必须在 OWL 加载完成后调用）
    inject_virtual_actions(loader)
    configure_loader(loader, model=self._config.model,
                     api_key=self._config.api_key,
                     base_url=self._config.base_url)

    mounted = list(view_codes or []) + list(object_codes or [])
    return loader, mounted
```

> **为什么用追加而非清空**：`_load_from_owl_content()`（全量加载路径）每次都 `clear()`，
> 不适合按需场景。`load_from_content()` 是追加语义，多次调用安全叠加。

---

### 4. 中断处理流程

#### 4.1 正常场景

```
ask(question, view_codes=["scene_sales"], object_codes=["by_customer"],
    thread_id="caller-generated-uuid")
    │
    ├─ key = _make_cache_key(view_codes, object_codes)
    ├─ _graph_cache.get(key) 命中？
    │      是 → 直接取出 compiled graph，跳过 OWL 解析和图构建
    │      否 ↓
    │          ├─ _build_loader(view_codes, object_codes)
    │          │      ├─ load_view_with_deps + load_object_with_deps → OntologyLoader（追加）
    │          │      ├─ inject_virtual_actions(loader)
    │          │      └─ configure_loader(loader, ...)
    │          ├─ OntologyToolLoader(mounted_objects=..., loader=...).load() → tools
    │          ├─ build_analysis_graph() + compile
    │          └─ _graph_cache[key] = compiled
    ├─ astream_events() 流式执行
    │      ├─ on_chat_model_stream（非 respond 节点）→ yield ThinkingEvent(chunk)
    │      └─ on_custom_event("step_title") → yield StepEvent(title)
    │
    ├─ 流结束后 aget_state（注意：去掉 checkpoint_id 后调用）
    │      └─ state.interrupts 为空
    │
    └─ 从 state.values["final_answer"] 提取答案
           └─ yield AnswerEvent(content)
```

#### 4.2 中断场景（PARADIGM_CLARIFICATION）

```
ask(question, view_codes=[...], thread_id="caller-generated-uuid")
    │
    ├─ ... (同上执行，直到 user_clarify_node 调用 interrupt())
    │
    ├─ astream_events() 流暂停
    ├─ aget_state（去掉 checkpoint_id）.interrupts 非空
    │      interrupt.value = {
    │          "reason_code": "PARADIGM_CLARIFICATION",
    │          "ask_user_payload": {"paradigmList": [...], "query": "..."},
    │          "prompt": "查询条件存在歧义，请确认查询维度"
    │      }
    │
    └─ yield InterruptEvent(
               thread_id="caller-generated-uuid",   ← 与 ask() 传入值一致
               reason="PARADIGM_CLARIFICATION",
               prompt="...",
               paradigm_list=[ParadigmGroup(...)]
           )
           ← 流结束，等待用户操作

# 用户在 UI 选择维度后：
resume(thread_id="caller-generated-uuid",
       user_input=ParadigmAnswer(...),
       view_codes=[...])   # 与 ask() 保持一致
    │
    ├─ ParadigmAnswer → LangGraph resume_value 格式转换
    │      {"paradigmList": [{"paradigmList": [chosen_items]}]}
    │
    ├─ Command(resume=resume_value)
    ├─ astream_events() 恢复执行
    └─ yield AnswerEvent(content)
```

#### 4.3 `aget_state` 调用细节

`aget_state` 必须去掉 `checkpoint_id` 后调用，否则查到的是特定历史快照，而非当前执行完毕后的最新状态：

```python
snapshot_config = {
    "configurable": {**run_config["configurable"]}
}
snapshot_config["configurable"].pop("checkpoint_id", None)   # 关键：去掉才能拿到最新状态
snapshot = await compiled.aget_state(snapshot_config)
```

#### 4.4 resume_value 格式转换

`user_clarify_node` 内部期望的格式：
```python
{"paradigmList": [{"paradigmList": [{"choiceKeyword": "华东", "recall": "east_china"}]}]}
```
`OntologyAgent.resume()` 负责处理两种 `user_input` 类型：
- `ParadigmAnswer`：转换为上述格式，作为 `Command(resume=resume_value)` 传入图
- `str`：直接以 `Command(resume=str_value)` 传入，对应 `ASK_USER` 场景的文本回复

#### 4.5 user_code 兼容

`user_clarify_node` 原通过 `config["configurable"]["gateway_context"]` 获取 `user_id`
用于同义词持久化。SDK 模式下将 `user_code` 直接写入 `config["configurable"]["user_code"]`，
并在 `user_clarify_node` 中增加兼容读取（约 3 行改动）。未提供时跳过持久化，其余逻辑不受影响。

---

### 5. 内部实现关键点

#### 5.1 OntologyAgent 内部结构

```
OntologyAgent
├── _config: OntologyAgentConfig
├── _graph_cache: OrderedDict[tuple[frozenset, frozenset], CompiledGraph]  # T6 进程级缓存
│
├── _build_loader(view_codes, object_codes) → (OntologyLoader, mounted: list[str])
│       ├─ OntologyLoader()
│       ├─ load_view_with_deps(resource_path, view_code)  ×N
│       ├─ load_object_with_deps(resource_path, obj_code) ×N
│       ├─ inject_virtual_actions(loader)
│       └─ configure_loader(loader, model, api_key, base_url)
│
├── _get_or_build_graph(view_codes, object_codes) → CompiledGraph  # T6 缓存入口
│       ├─ key = _make_cache_key(view_codes, object_codes)
│       ├─ 命中 → move_to_end + 直接返回
│       └─ 未命中 → _build_loader → build_graph → compile → 写缓存 → 返回
│
├── _iter_events(compiled, input_payload, run_config) → AsyncGenerator[OntologyAgentEvent, None]
│       ├─ astream_events(version="v2") 消费原始事件
│       │      ├─ on_chat_model_stream（metadata["langgraph_node"] != "respond"）→ yield ThinkingEvent(chunk)
│       │      └─ on_custom_event("step_title") → yield StepEvent(title)
│       ├─ 流结束后 aget_state（去掉 checkpoint_id，见 §4.3）
│       ├─ interrupts 非空 → yield InterruptEvent，结束
│       └─ interrupts 为空 → 从 state.values["final_answer"] 提取 → yield AnswerEvent，结束
│
├── ask()    → _get_or_build_graph → _iter_events
└── resume() → _get_or_build_graph → Command(resume=...) → _iter_events
```

> **ThinkingEvent 过滤说明**：`on_chat_model_stream` 事件通过
> `event["metadata"]["langgraph_node"] != "respond"` 过滤，仅保留 `respond` 节点**之外**
> 的 LLM 增量 token 作为思考过程。`respond` 节点的答案通过 `state.values["final_answer"]`
> 提取，不从流中重复读取。

> **答案推送说明**：初始版本 `AnswerEvent` 在 `astream_events` 结束后一次性 yield，
> 不做增量推送。`respond` 节点的 LLM 流（`on_chat_model_stream`）仅在未来版本启用
> `AnswerChunkEvent` 后使用，初始版本跳过。

#### 5.2 与 runner.py 的关系

`runner.py` 使用 `stream_mode="values"`（完整状态快照），适合批处理。
`OntologyAgent` 内部改用 `astream_events(version="v2")`，拿增量 LLM token，
实现真正的流式思考过程。两者并行存在，分别服务不同场景。

---

### 6. worker.py 重构（T5）

#### 6.1 新增配置项：`_resource_path`

`DataCloudWorker.__init__` 新增一个属性，用于构造 `OntologyAgentConfig`：

```python
self._resource_path: str = os.environ.get("DATACLOUD_ONTOLOGY_PATH", "")
```

`start_heartbeat()` 中初始化 `OntologyAgent` 时，若 `resource_path` 为空则立即抛出 `ValueError`，
在 worker 就绪前即可发现，而非等到第一次请求时才报错。

#### 6.2 Phase 1：动态路径改用 OntologyAgent

**改动范围**：`start_heartbeat()` 初始化 + `_is_dynamic_agent == True` 时的分支（约 50 行）。

`OntologyAgent` 必须作为**长生命周期对象**在 worker 启动时创建一次，跨请求复用。
若在每次请求中新建实例，T6 的进程级图缓存将在每次请求后丢失，缓存失效。

```python
# start_heartbeat() 中初始化（新增）
self._ontology_agent = OntologyAgent(
    OntologyAgentConfig(
        api_key=self.api_key or "",
        model=self.model_name or "",
        base_url=self.base_url,
        resource_path=self._resource_path,
    )
)

# process_command() 中动态路径分支
if _is_dynamic_agent:
    thread_id = self._build_thread_id(
        session_id=context.session_id,
        agent_key=runtime_agent_key,
    )

    if isinstance(command, ResumeCommand) or _paradigm_resume_value is not None:
        raw_paradigm = _paradigm_resume_value or command.reply_data
        resume_input: str | ParadigmAnswer = _dict_to_paradigm_answer(raw_paradigm)
        event_iter = self._ontology_agent.resume(
            thread_id, resume_input,
            view_codes=_dyn_view_ids,
            object_codes=_dyn_object_ids,
        )
    else:
        event_iter = self._ontology_agent.ask(
            question=latest_user_text,
            view_codes=_dyn_view_ids,
            object_codes=_dyn_object_ids,
            thread_id=thread_id,
            user_code=_get_gateway_user_code(context),
        )

    return await _consume_agent_events(event_iter, context, reco_task)
```

**三个新增 helper 说明**：

| helper | 位置 | 说明 |
|--------|------|------|
| `_dict_to_paradigm_answer(raw)` | worker.py 新增 | 将前端回传的 `{"paradigmList": [...]}` dict 转为 `ParadigmAnswer`；若 raw 为 str 直接包装返回 |
| `_get_gateway_user_code(context)` | worker.py 新增，复用现有逻辑 | 调用 `get_gateway_user_id(context)`（已有 helper）提取用户标识 |
| `_consume_agent_events(iter, ctx, reco)` | worker.py 新增 | 消费事件流并翻译为 Gateway SSE，返回 `{"status": "done"}` 或 `{"status": "waiting"}` |

**`_consume_agent_events` 事件映射**：

| OntologyAgentEvent | Gateway 操作 | 返回值 |
|--------------------|-------------|--------|
| `ThinkingEvent` | `context.emit_chunk(..., REASONING_LOG_START, think_text)` | 继续 |
| `StepEvent` | `context.emit_chunk(..., REASONING_LOG_START, think_text)` | 继续 |
| `AnswerEvent` | `context.emit_chunk(..., ANSWER_DELTA, text)` → `flush_to_history()` → `emit_chunk(..., APP_STREAM_RESPONSE, "回答完成")` | `{"status": "done"}` |
| `InterruptEvent(PARADIGM_CLARIFICATION)` | `emit_chunk(..., APP_STREAM_RESPONSE, "回答完成")` → `context.complex_ask_user(AskUserEvent(...))` | `{"status": "waiting"}` |
| `InterruptEvent(AGENT_DELEGATE_WAIT)` | `emit_chunk(..., APP_STREAM_RESPONSE, "回答完成")` → 静默，不回调用户 | `{"status": "waiting"}` |
| `InterruptEvent(其他)` | `emit_chunk(..., APP_STREAM_RESPONSE, "回答完成")` → `context.ask_user(AskUserEvent(...))` | `{"status": "waiting"}` |
| `ErrorEvent` | `logger.error(...)` → emit 错误内容 | `{"status": "done"}` |

#### 6.3 Phase 2：静态路径重构（规划）

静态路径依赖 `AgentConfig` 中的 `prompts_dict`、`tools_dict`、`skip_action_families`，
需要 `OntologyAgentConfig` 扩展支持这些参数后才能迁移。

暂时**保留现有静态路径不变**，等 Phase 1 稳定后再规划。

#### 6.4 保留在 worker.py 的职责

重构后以下逻辑**不迁入 OntologyAgent**：

- **协议解析**：`GatewayCommand` / `ResumeCommand` → question / view_codes / object_codes / thread_id
- **Agent config 加载**：从 `plugin_registry` 动态加载 `AgentConfig`
- **Resume 幂等去重**：`_resume_result_cache` + `_resume_inflight`（去重检查在 `_is_dynamic_agent` 分支**之前**执行，动态路径天然受益，T5 重构不影响此逻辑）
- **闲聊检测**：`_is_light_chitchat()` 快速回复
- **推荐问题任务**：`reco_plugin.generate_recommended_questions()` 后台并发
- **心跳保活**：`_heartbeat_loop()`
- **静态路径 Graph 缓存**：LRU `self.graphs`（动态路径迁 OntologyAgent 后此缓存不再覆盖动态场景）

---

### 7. OntologyAgent 进程级图缓存（T6）

#### 7.1 背景与问题

`datacloud-analysis` 包内部 `create_agent()` / `build_analysis_graph()` / `graph.compile()` 均**无缓存**，每次调用都重新构建并编译图。

T5 重构后动态路径的每次请求开销：

| 步骤 | 说明 | 估计耗时 |
|------|------|---------|
| 解析 OWL 文件 | `load_view_with_deps` + `load_object_with_deps` | 数十 ms ~ 数百 ms（取决于文件数） |
| 构建 StateGraph | `build_analysis_graph()` | 数十 ms |
| 编译图 | `graph.compile(checkpointer=...)` | 数十 ms |

重构前动态路径使用 `self.graphs["dynamic:{sha1}"]` LRU 缓存，上述三步在相同 `view_codes` 组合下只执行一次。T5 后若不补缓存，动态路径每次请求都有这三步开销，存在明显性能退步。

#### 7.2 缓存设计

**缓存位置**：`OntologyAgent` 实例内部，实例需长生命周期（见 §6.2）。

**缓存内容**：

```python
# OntologyAgent 内部
_graph_cache: OrderedDict[tuple[frozenset[str], frozenset[str]], Any]  # compiled graph
_CACHE_MAX: int = 32   # 与 worker.py 原有上限对齐
```

**缓存 key**：

```python
def _make_cache_key(
    view_codes: list[str] | None,
    object_codes: list[str] | None,
) -> tuple[frozenset[str], frozenset[str]]:
    return (frozenset(view_codes or []), frozenset(object_codes or []))
```

view_codes 和 object_codes 分开放入两个 frozenset，避免 `view_code="x"` 与 `object_code="x"` 碰撞。

**缓存读写流程**：

```
ask(view_codes, object_codes, ...)
    │
    ├─ key = _make_cache_key(view_codes, object_codes)
    │
    ├─ _graph_cache.get(key) 命中？
    │      是 → 直接取出 compiled graph，跳过 OWL 解析和图构建
    │      否 ↓
    │
    ├─ _build_loader(view_codes, object_codes)   # OWL 解析
    ├─ build_analysis_graph() + graph.compile()  # 图构建和编译
    ├─ _graph_cache[key] = compiled              # 写入图缓存
    │      （超过 CACHE_MAX 时 LRU 淘汰最旧条目）
    │
    └─ _iter_events(compiled, ...)
```

**LRU 淘汰**：使用 `collections.OrderedDict`，命中时 `move_to_end`，超限时 `popitem(last=False)`，与 `worker.py` 现有实现一致。

**并发 cache miss**：初始版本不加锁。并发请求同时 miss 同一 key 时，多个协程各自构建图并
各自写入缓存，最后写入者获胜；结果始终正确，仅有一次轻微的重复构建开销。
OWL 文件只读，无竞争条件。

#### 7.3 缓存失效策略

初始版本**无主动失效机制**，进程重启即清空。适用前提：
- OWL 文件在运行时不会变更（由部署约定保证）
- 需要热更新 OWL 时，重启进程即可

后续可按需扩展：
- 文件变更监听（`watchfiles`）触发指定 key 失效
- 外部管理接口（HTTP endpoint）触发全量或按 view_code 失效

#### 7.4 SDK 直调场景

第三方直接使用 `OntologyAgent` 时，**自行管理实例生命周期**即可享受缓存收益：

```python
# 应用启动时创建一次，存为全局/单例
agent = OntologyAgent(config)

# 后续每次请求复用同一实例
async for event in agent.ask(question=..., view_codes=["scene_sales"]):
    ...
```

不建议在每次请求时 `OntologyAgent(config)` —— 那样图缓存在每次请求后即丢失，退化为无缓存模式。

---

## 验收用例

### Demo 目录结构

```
examples/chatbi_demo/
├── pyproject.toml          # 依赖：datacloud-analysis（本地路径）
├── README.md
├── demo_normal.py          # 场景一：正常流程（无中断）
└── demo_interrupt.py       # 场景二：中断 + 用户确认 + 恢复
```

### 场景一：正常流程

```python
# examples/chatbi_demo/demo_normal.py
import asyncio
import uuid
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

    # 多轮对话：调用方自行生成并持久化 thread_id
    thread_id = str(uuid.uuid4())

    async for event in agent.ask(
        question="各部门本月销售额是多少？",
        view_codes=["scene_sales"],
        thread_id=thread_id,
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

**验收标准**：
- 控制台持续打印思考过程（ThinkingEvent）
- 出现 `[问题理解]` / `[任务执行]` 等阶段标题（StepEvent）
- 流结束时打印完整答案（AnswerEvent）
- 全程无异常、无中断

### 场景二：中断 + 用户确认 + 恢复

```python
# examples/chatbi_demo/demo_interrupt.py
import asyncio
import uuid
from collections.abc import AsyncGenerator
from datacloud_analysis.ontology_agent import (
    OntologyAgent, OntologyAgentConfig, OntologyAgentEvent,
    ThinkingEvent, StepEvent, AnswerEvent, ErrorEvent, InterruptEvent,
    ParadigmAnswer, ParadigmGroupSelection,
)

async def stream_until_interrupt(
    iterator: AsyncGenerator[OntologyAgentEvent, None],
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

    # 调用方持有 thread_id，两轮共用同一个
    thread_id = str(uuid.uuid4())

    # 第一轮：发起问题
    print("问：华东区域的销售额是多少？\n")
    interrupt_event = await stream_until_interrupt(
        agent.ask(
            question="华东区域的销售额是多少？",
            view_codes=view_codes,
            thread_id=thread_id,
            user_code="user_001",
        )
    )
    if interrupt_event is None:
        return

    # 用户选择
    user_answer = mock_user_select(interrupt_event)

    # 第二轮：恢复（thread_id 与 view_codes 与 ask() 保持一致）
    print("\n[继续执行...]\n")
    await stream_until_interrupt(
        agent.resume(
            thread_id=thread_id,
            user_input=user_answer,
            view_codes=view_codes,
            user_code="user_001",
        )
    )

asyncio.run(main())
```

**验收标准**：
- 第一轮流结束时收到 `InterruptEvent`，打印 `[需要澄清]` 和维度选项
- `resume()` 后流继续执行并输出最终答案（`AnswerEvent`）
- 全程无异常

---

### 场景三：worker.py 动态路径 — 正常问答（T5）

**测试方式**：通过 Gateway 向 `DataCloudWorker` 发送 `AskAgentCommand`

**前置条件**：
- 环境变量 `DATACLOUD_ONTOLOGY_PATH` 已指向有效 resource 目录
- resource 目录下存在 `view/scene_sales/` 子目录

**请求报文关键字段**：
```json
{
  "extra_payload": {
    "call_view_ids": ["scene_sales"]
  },
  "content": "各部门本月销售额是多少？"
}
```

**验收标准**：
- `process_command` 进入 `_is_dynamic_agent == True` 分支（日志可见 `dynamic agent path activated`）
- SSE 流中收到 `REASONING_LOG_START` 事件（思考过程）
- SSE 流中收到 `ANSWER_DELTA` 事件（最终答案内容非空）
- `process_command` 返回 `{"status": "done"}`
- 日志中**不出现** `_build_graph` / `AgentConfig` 相关调用（确认走了 OntologyAgent 路径）

---

### 场景四：worker.py 动态路径 — 维度澄清中断（T5）

**前置条件**：同场景三，问题能触发 `user_clarify_node` 的 `PARADIGM_CLARIFICATION` 中断

**请求报文**：
```json
{
  "extra_payload": {
    "call_view_ids": ["scene_sales"]
  },
  "content": "华东区域的销售额是多少？"
}
```

**验收标准**：
- SSE 流中收到思考过程（`REASONING_LOG_START`）
- `complex_ask_user` 被调用，回调 payload 包含：
  - `metadata.paradigmList`：非空列表，每项含 `name` 和选项
  - `metadata.thread_id`：非空字符串（格式为 `{agent_key}:{session_id}`）
  - `metadata.checkpoint_id`：非空字符串
  - `metadata.interrupt_reason`：值为 `"PARADIGM_CLARIFICATION"`
- `process_command` 返回 `{"status": "waiting"}`

---

### 场景五：worker.py 动态路径 — 中断恢复（T5）

**前置条件**：场景四执行完毕，已获取 `thread_id`、`checkpoint_id`、`checkpoint_ns`

**请求报文**（前端回传 paradigm 选择，使用 `AskAgentCommand` + `humanInput`）：
```json
{
  "extra_payload": {
    "call_view_ids": ["scene_sales"],
    "ext_params": {
      "humanInput": {
        "paradigmList": [
          {"paradigmList": [{"choiceKeyword": "华东", "recall": "east_china"}]}
        ],
        "metadata": {
          "thread_id": "<场景四返回的 thread_id>",
          "checkpoint_id": "<场景四返回的 checkpoint_id>",
          "checkpoint_ns": "<场景四返回的 checkpoint_ns>"
        }
      }
    }
  }
}
```

**验收标准**：
- 日志可见 `AskAgentCommand carries paradigm reply, converting to graph resume`
- `_dict_to_paradigm_answer` 正确将 `paradigmList` 转为 `ParadigmAnswer`（日志或断点验证）
- 图从中断点恢复执行，SSE 流中再次出现 `REASONING_LOG_START`
- SSE 流中收到 `ANSWER_DELTA`，答案包含"华东"相关内容
- `process_command` 返回 `{"status": "done"}`

---

### 场景六：静态路径回归（T5）

验证重构后静态路径（`agent_id` 匹配 `AgentConfig`）行为与重构前完全一致。

**前置条件**：`plugin_registry` 中已加载 `agent_id=10001` 的 `AgentConfig`

**请求报文**：
```json
{
  "extra_payload": {
    "agent_id": "10001"
  },
  "content": "查询本月销售数据"
}
```

**验收标准**：
- `_is_dynamic_agent == False`（日志中无 `dynamic agent path activated`）
- 走原有 `_build_graph` + `_stream_graph` 路径
- SSE 事件序列与重构前一致
- `process_command` 返回 `{"status": "done"}`

> 此场景为**回归测试**，用于保证重构没有破坏静态路径。

---

### 场景七：配置缺失兜底（T5）

**前置条件**：环境变量 `DATACLOUD_ONTOLOGY_PATH` **未设置**或为空

**请求报文**：`call_view_ids` 非空（触发动态路径）

**验收标准**：
- `OntologyAgent` 初始化时抛出明确异常（如 `ValueError: resource_path is required`）
- 错误日志可见，包含明确说明
- 不出现静默失败或空答案返回
