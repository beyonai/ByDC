# openClaw接入方案

## 需求描述

1.从 header_metadata 中获取 header_metadata["object_ids"]、header_metadata["view_ids"]
参数，数据样例如下：

header_metadata["object_ids"] = ["ads_grid_analysis"]
header_metadata["view_ids"] = ["scene_enterprise_analysis_definition"]

2、如果 header_metadata["object_ids"] 或 header_metadata["view_ids"]，则不再根据by_agent_id 的配置文件来构建，而是动态创建agent，把header_metadata["object_ids"]  、header_metadata["view_ids"] 作为tools挂载上去。

## 概要设计

### 背景与现状

当前 `DataCloudWorker.process_command` 的 Agent 构建流程是**静态配置路径**：

```
process_command
  → 读取 by_agent_id（来自 header_metadata / extra_payload）
  → 从 context.list_agent_configs() 按 agent_id 匹配 AgentConfig
  → 取出 AgentConfig.extra 中的 prompts_dict / tools_dict / mounted_objects / loader
  → _build_graph(prompts_dict, tools_dict, mounted_objects, loader)
  → 缓存到 self.graphs["{agent_id}:{conf_hash}"]
```

所有可用的 OBJECT / VIEW 资源在 Worker 启动阶段由 `InitAgentConfPlugin` 预先解析，
写入 `AgentConfig.extra["mounted_objects"]` 和 `AgentConfig.extra["loader"]`。

### 整体方案

在 `process_command` 中增加一条**动态 Agent 路径**，与现有静态路径并列：
- 若 `header_metadata` 中存在非空的 `object_ids` 或 `view_ids`，进入动态路径；
- 否则保持现有静态路径，不做任何改动。

两条路径最终都调用相同的 `_build_graph` 接口，共享后续的 LangGraph 执行流程，
因此动态路径**不涉及 graph 内部结构的任何修改**。

```
process_command
  │
  ├─ 读取 header_metadata
  ├─ 检查 object_ids / view_ids
  │
  ├─ [均为空] ─────────────────────────────────────────────── 静态路径（现有逻辑）
  │             → 按 by_agent_id 查 AgentConfig
  │             → 取 prompts / tools / mounted_objects / loader
  │             → cache_key = "{agent_id}:{conf_hash}"
  │             → _build_graph(...)
  │
  └─ [任一非空] ───────────────────────────────────────────── 动态路径（新增）
                → mounted_objects = dedup(object_ids + view_ids)
                → loader = _get_shared_loader()
                → prompts_dict = _get_dynamic_default_prompts()
                → cache_key = "dynamic:{resource_fingerprint}"
                → _build_graph(mounted_objects, loader, prompts_dict)
```

### 关键设计点

#### 1. 动态路径触发判断

位置：`worker.py` → `process_command`，在读取 `header_metadata` 之后立即判断。

```python
_dyn_object_ids: list[str] = list(header_metadata.get("object_ids") or [])
_dyn_view_ids:   list[str] = list(header_metadata.get("view_ids") or [])
_is_dynamic_agent = bool(_dyn_object_ids or _dyn_view_ids)
```

若 `_is_dynamic_agent` 为 True，跳过 `AgentConfig` 查找，进入动态构建逻辑。

#### 2. mounted_objects 组装

将 `object_ids` 与 `view_ids` 合并去重，顺序为 object_ids 在前、view_ids 在后：

```python
_seen: set[str] = set()
mounted_objects: list[str] = []
for code in _dyn_object_ids + _dyn_view_ids:
    if code and code not in _seen:
        mounted_objects.append(code)
        _seen.add(code)
```

`OntologyToolLoader.load()` 已支持 OBJECT 与 VIEW 两种类型，无需额外适配。

#### 3. 共享 Loader 获取策略

动态 Agent 需要 `OntologyLoader` 来加载 OWL 本体数据。采用**三级降级策略**：

1. **复用已加载 AgentConfig 的 loader**（优先）：
   从 `context.list_agent_configs()` 中取第一个含有 `extra["loader"]` 的 AgentConfig。
   同一部署环境下所有 Agent 共享同一份 OWL scene，loader 可以复用。

2. **Worker 级别 shared_loader**（次选）：
   `DataCloudWorker` 新增 `_shared_loader: Any | None` 属性，在 `start_heartbeat` 完成
   `InitAgentConfPlugin` 初始加载后，从加载结果中取第一个可用 loader 保存。
   若后续静态 AgentConfig 均不含 loader，则动态路径从此处取。

3. **loader=None 兜底**：
   `OntologyToolLoader` 在 `loader=None` 时会跳过 OWL 注入，仅能挂载无需 OWL 数据的简单工具。
   记录 warning 日志，不阻断流程。

#### 4. 动态 Agent 的系统提示词

动态路径不绑定任何 `by_agent_id` 的配置文件，系统提示词来源：

- 使用 Worker 内置的**通用 DataCloud 系统提示词**（已在 `datacloud_analysis` 中定义）。
- `prompts_dict` 传空（`None`），由 `build_analysis_graph` 内部应用默认 prompts。
- 如需定制，可在 `header_metadata` 中增加 `system_prompt_override` 字段（预留扩展，本期不实现）。

#### 5. Graph 缓存策略

动态路径的 cache_key 基于**资源指纹**而非 `agent_id`，确保相同资源集合复用同一 graph：

```python
_resource_fingerprint = hashlib.sha1(
    "|".join(sorted(mounted_objects)).encode()
).hexdigest()[:12]
cache_key = f"dynamic:{_resource_fingerprint}"
```

缓存容量复用现有 `self.graphs`（`OrderedDict` + LRU 淘汰），无需额外改动缓存机制。

#### 6. ResumeCommand 兼容

`ResumeCommand` 的 `header_metadata` 中需携带与原始请求相同的 `object_ids` / `view_ids`，
由调用方（前端 / 上游 gateway）负责透传。

动态路径与静态路径的 Resume 逻辑无差异：相同 `cache_key` 命中同一 graph，
LangGraph checkpoint 通过 `thread_id` 恢复状态，无需额外处理。

#### 7. 禁用推荐问题插件

`RecommendedQuestionsPlugin`（`datacloud_recommended_questions`）的系统提示词与字段知识是
针对特定业务场景（企业/网格分析）硬编码的，与动态挂载的任意 OBJECT / VIEW 资源**无关联性**，
贸然运行会产生语义错误的推荐问题。

**处理方式**：在 `process_command` 中，创建 `reco_task` 的代码块已通过 `_is_dynamic_agent`
标志短路——动态路径下直接将 `reco_task` 设为 `None`，跳过插件调用：

```python
reco_task: asyncio.Task[list[str]] | None = None
if not _is_dynamic_agent:            # 动态路径不启用推荐问题
    reco_plugin = (
        self.plugin_registry.get_plugin("datacloud_recommended_questions")
        if self.plugin_registry else None
    )
    if reco_plugin is not None and bool(getattr(reco_plugin.manifest, "enabled", True)):
        gen_fn = getattr(reco_plugin, "generate_recommended_questions", None)
        if callable(gen_fn):
            rq = _latest_user_text_from_content(command.content).strip()
            if rq:
                reco_task = asyncio.create_task(gen_fn(rq))
```

`reco_task=None` 传入 `_stream_graph` 后，推荐问题结果不会被推送给前端。

#### 8. 参数校验与错误处理

| 异常场景 | 处理方式 |
|---------|---------|
| `object_ids` / `view_ids` 包含非字符串元素 | 过滤非字符串，记录 warning |
| `object_ids` / `view_ids` 包含未知资源码 | `OntologyToolLoader` 内部已处理（跳过 + 记录 debug），不报错 |
| loader 三级均不可用 | `loader=None` 降级，记录 warning，继续执行 |
| `object_ids` 与 `view_ids` 均为空列表 | 视为未传，走静态路径 |

### 改动范围

本方案改动**仅限** `byclaw-data/src/byclaw_data/worker.py`，最小化对现有逻辑的侵入：

| 改动点 | 类型 | 说明 |
|-------|------|------|
| `DataCloudWorker.__init__` | 新增属性 | `_shared_loader: Any \| None = None` |
| `start_heartbeat` | 新增逻辑 | 初始加载完成后保存 shared_loader |
| `process_command` | 新增分支 | 动态路径检测、graph 构建、reco_task 屏蔽（约 50 行） |

**不改动**：`init_agent_conf.py`、`agent.py`、`OntologyToolLoader`、`graph_builder.py`、
`AgentState`、任何 graph 内部节点、`RecommendedQuestionsPlugin` 自身。

### 数据流示意

```
前端 / OpenClaw
  │
  │  AskAgentCommand
  │  header.metadata = {
  │    "agent_id": "...",          ← 可选，动态路径下忽略
  │    "object_ids": ["ads_grid_analysis"],
  │    "view_ids":   ["scene_enterprise_analysis_definition"]
  │  }
  │
  ▼
DataCloudWorker.process_command
  │
  ├─ _is_dynamic_agent = True
  ├─ mounted_objects = ["ads_grid_analysis", "scene_enterprise_analysis_definition"]
  ├─ loader = _get_shared_loader()   ← 复用已有 loader
  ├─ cache_key = "dynamic:a3f9c12b84d1"
  │
  ▼
_build_graph(mounted_objects=["ads_grid_analysis", "scene_enterprise_analysis_definition"],
             loader=loader, prompts_dict=None)
  │
  ▼
create_agent → OntologyToolLoader.load()
  ├─ ads_grid_analysis    → query_ads_grid_analysis / analyze_ads_grid_analysis / ...
  └─ scene_enterprise_..  → query_scene_enterprise_... / analyze_scene_enterprise_... / ...
  │
  ▼
LangGraph graph（ReAct 正常执行）
```

## 详细设计

> 涉及文件：`byclaw-data/src/byclaw_data/worker.py`（唯一修改文件）

---

### 3.1 `DataCloudWorker.__init__` — 新增 `_shared_loader` 属性

**位置**：`__init__` 方法末尾（当前约第 268 行，`self.command_plugin_manager = ...` 之后）

```python
# 新增：动态 Agent 路径使用的全局共享 OntologyLoader
self._shared_loader: Any | None = None
```

---

### 3.2 新增辅助方法 `_extract_shared_loader`

**位置**：`DataCloudWorker` 类内，`_build_graph` 方法附近

```python
def _extract_shared_loader(self) -> Any | None:
    """从已加载的 AgentConfig 中取第一个可用的 OntologyLoader 供动态路径复用。

    所有静态 Agent 共享同一份 OWL scene，loader 可跨 Agent 复用。
    三级降级：AgentConfig.extra["loader"] → self._shared_loader → None。
    """
    for cfg in (self.plugin_registry.agent_configs if self.plugin_registry else []):
        extra = getattr(cfg, "extra", None) or {}
        loader = extra.get("loader")
        if loader is not None:
            return loader
    if self._shared_loader is not None:
        return self._shared_loader
    logger.warning(
        "DataCloudWorker._extract_shared_loader: no loader found in any AgentConfig; "
        "dynamic agent will proceed with loader=None (OWL injection skipped)"
    )
    return None
```

---

### 3.3 `start_heartbeat` — 初始化 `_shared_loader`

**位置**：`start_heartbeat` 方法末尾（当前约第 757 行，`await bootstrap.setup()` 之后）

```python
# 动态路径：从首个已加载 AgentConfig 取 loader 并缓存至 worker 级别
self._shared_loader = self._extract_shared_loader()
logger.info(
    "DataCloudWorker: _shared_loader=%s",
    "ready" if self._shared_loader is not None else "None (dynamic agents will skip OWL inject)",
)
```

---

### 3.4 `process_command` — 动态路径标志检测

**位置**：`header_metadata` 读取之后（当前约第 824 行），`by_agent_id` 提取之前

```python
# ── 动态 Agent 路径检测 ──────────────────────────────────────────────────────
_dyn_object_ids: list[str] = [
    s.strip()
    for s in (header_metadata.get("object_ids") or [])
    if isinstance(s, str) and s.strip()
]
_dyn_view_ids: list[str] = [
    s.strip()
    for s in (header_metadata.get("view_ids") or [])
    if isinstance(s, str) and s.strip()
]
_is_dynamic_agent: bool = bool(_dyn_object_ids or _dyn_view_ids)
if _is_dynamic_agent:
    logger.info(
        "DataCloudWorker: dynamic agent path activated "
        "session=%s object_ids=%s view_ids=%s",
        context.session_id,
        _dyn_object_ids,
        _dyn_view_ids,
    )
```

---

### 3.5 `process_command` — 跳过 `_ensure_agent_config_loaded`

**位置**：当前约第 886 行（`target_agent_id_for_load = ...` 处）

```python
# 动态路径不依赖 AgentConfig，跳过配置预加载
if not _is_dynamic_agent:
    target_agent_id_for_load = str(by_agent_id or runtime_agent_key or "").strip()
    await self._ensure_agent_config_loaded(
        context=context,
        command=command,
        agent_id=target_agent_id_for_load,
    )
```

---

### 3.6 `process_command` — 替换 AgentConfig 查找 + 资源提取 + graph 构建

**位置**：当前约第 1012 行（`agent_configs = context.list_agent_configs()` 处）

用 `if _is_dynamic_agent: ... else: ...` 包裹整个"查找配置 → 提取资源 → 计算 conf_hash → 构建 graph"块：

```python
if _is_dynamic_agent:
    # ── 动态路径：直接组装 mounted_objects ──────────────────────────────────
    _seen: set[str] = set()
    mounted_objects: list[str] = []
    for _code in _dyn_object_ids + _dyn_view_ids:
        if _code not in _seen:
            mounted_objects.append(_code)
            _seen.add(_code)

    ontology_loader = self._extract_shared_loader()
    prompts_dict: dict[str, Any] = {}
    tools_dict: dict[str, Any] = {}
    skip_action_families: frozenset[str] = frozenset()

    _fingerprint = hashlib.sha1(
        "|".join(sorted(mounted_objects)).encode()
    ).hexdigest()[:12]
    conf_hash = _fingerprint
    cache_key = f"dynamic:{_fingerprint}"

    logger.info(
        "DataCloudWorker: dynamic agent session=%s "
        "mounted_objects=%s loader_ready=%s cache_key=%s",
        context.session_id,
        mounted_objects,
        ontology_loader is not None,
        cache_key,
    )

    target_graph = self.graphs.get(cache_key)
    if not target_graph:
        target_graph = self._build_graph(
            mounted_objects=mounted_objects,
            loader=ontology_loader,
            agent_id="dynamic",
        )
        self.graphs[cache_key] = target_graph
        while len(self.graphs) > self._GRAPH_CACHE_MAX:
            evicted_key, _ = self.graphs.popitem(last=False)
            logger.info("Graph cache evicted: key=%s", evicted_key)
    else:
        self.graphs.move_to_end(cache_key)

else:
    # ── 静态路径（现有代码原封不动）────────────────────────────────────────
    agent_configs = context.list_agent_configs()
    config_for_this_call = next(
        (cfg for cfg in agent_configs if str(cfg.agent_id) == str(by_agent_id)),
        None,
    )
    # ... 以下保持现有逻辑不变，直至 target_graph 缓存逻辑结束 ...
```

> **注意**：`by_agent_id`、`conf_hash`、`cache_key`、`target_graph` 四个变量在两条路径中
> 均已赋值，后续代码（thread_id、config dict、graph_input 等）**不需要任何改动**。

---

### 3.7 `process_command` — 屏蔽推荐问题插件

**位置**：当前约第 1287 行（`reco_task: asyncio.Task[list[str]] | None = None` 处）

```python
reco_task: asyncio.Task[list[str]] | None = None
if not _is_dynamic_agent:                        # ← 仅静态路径启用推荐问题
    reco_plugin = (
        self.plugin_registry.get_plugin("datacloud_recommended_questions")
        if self.plugin_registry
        else None
    )
    if reco_plugin is not None and bool(
        getattr(reco_plugin.manifest, "enabled", True)
    ):
        gen_fn = getattr(reco_plugin, "generate_recommended_questions", None)
        if callable(gen_fn):
            rq = _latest_user_text_from_content(command.content).strip()
            if rq:
                reco_task = asyncio.create_task(gen_fn(rq))
```

---

### 3.8 修改点汇总

| # | 方法 | 当前行（参考） | 改动类型 | 说明 |
|---|------|-------------|---------|------|
| 1 | `__init__` | ~268 | 新增属性 | `self._shared_loader = None` |
| 2 | 类级别 | `_build_graph` 附近 | 新增方法 | `_extract_shared_loader()` |
| 3 | `start_heartbeat` | ~758 | 新增逻辑 | 初始化 `self._shared_loader` |
| 4 | `process_command` | ~824 | 新增代码段 | 检测 `_is_dynamic_agent` 标志 |
| 5 | `process_command` | ~886 | 条件包裹 | `if not _is_dynamic_agent:` 跳过 `_ensure_agent_config_loaded` |
| 6 | `process_command` | ~1012 | 条件分支 | `if/else` 包裹 AgentConfig 查找至 graph 构建（约 150 行） |
| 7 | `process_command` | ~1287 | 条件包裹 | `if not _is_dynamic_agent:` 屏蔽 reco_task 创建 |

---

### 3.9 验收测试用例

以下测试用例通过调用 `process_command` 或直接检查中间状态进行验证。
单元测试中以 stub/mock 替换 `_build_graph`、`_stream_graph`、`_extract_shared_loader`。

#### TC-01 — 动态路径：仅 object_ids

| 项 | 内容 |
|----|------|
| **前置条件** | Worker 已完成 `start_heartbeat`；`plugin_registry` 中存在至少一个静态 AgentConfig |
| **输入** | `header_metadata = {"object_ids": ["ads_grid_analysis"]}` |
| **执行** | `process_command(AskAgentCommand, context)` |
| **期望** | `_build_graph` 被调用，`mounted_objects=["ads_grid_analysis"]`；`cache_key` 以 `"dynamic:"` 开头；`_ensure_agent_config_loaded` 未被调用 |

#### TC-02 — 动态路径：仅 view_ids

| 项 | 内容 |
|----|------|
| **输入** | `header_metadata = {"view_ids": ["scene_enterprise_analysis_definition"]}` |
| **期望** | `mounted_objects=["scene_enterprise_analysis_definition"]`；`cache_key` 以 `"dynamic:"` 开头 |

#### TC-03 — 动态路径：object_ids + view_ids 同时存在

| 项 | 内容 |
|----|------|
| **输入** | `header_metadata = {"object_ids": ["obj_a", "obj_b"], "view_ids": ["view_c"]}` |
| **期望** | `mounted_objects=["obj_a", "obj_b", "view_c"]`（object_ids 在前，顺序稳定） |

#### TC-04 — 静态路径不受影响

| 项 | 内容 |
|----|------|
| **输入** | `header_metadata = {"agent_id": "some_static_agent"}` （无 `object_ids` / `view_ids`） |
| **期望** | 走原有 AgentConfig 查找逻辑；`_is_dynamic_agent=False`；`_build_graph` 使用 AgentConfig 中的配置 |

#### TC-05 — object_ids / view_ids 均为空列表，退回静态路径

| 项 | 内容 |
|----|------|
| **输入** | `header_metadata = {"object_ids": [], "view_ids": [], "agent_id": "x"}` |
| **期望** | `_is_dynamic_agent=False`，走静态路径 |

#### TC-06 — 重复资源码去重

| 项 | 内容 |
|----|------|
| **输入** | `header_metadata = {"object_ids": ["obj_a", "obj_a"], "view_ids": ["obj_a", "view_b"]}` |
| **期望** | `mounted_objects=["obj_a", "view_b"]`（`obj_a` 只出现一次） |

#### TC-07 — 非字符串元素过滤

| 项 | 内容 |
|----|------|
| **输入** | `header_metadata = {"object_ids": ["obj_a", None, 123, "", "obj_b"]}` |
| **期望** | `mounted_objects=["obj_a", "obj_b"]`（`None`/数字/空字符串均被过滤） |

#### TC-08 — Graph 缓存命中：相同资源集合复用同一 graph

| 项 | 内容 |
|----|------|
| **步骤** | 1. 第一次请求 `object_ids=["obj_a"]` → `_build_graph` 被调用一次，graph 写入缓存<br>2. 第二次请求 `object_ids=["obj_a"]` → `_build_graph` **不再被调用**，直接复用缓存 |
| **期望** | `_build_graph` 全程仅被调用 **1 次** |

#### TC-09 — 动态路径不触发推荐问题插件

| 项 | 内容 |
|----|------|
| **前置条件** | `datacloud_recommended_questions` 插件已注册且 `enabled=True` |
| **输入** | `header_metadata = {"object_ids": ["obj_a"]}` |
| **期望** | `generate_recommended_questions` 方法**未被调用**；`reco_task=None` 传入 `_stream_graph` |

#### TC-10 — 静态路径仍触发推荐问题插件

| 项 | 内容 |
|----|------|
| **输入** | `header_metadata = {"agent_id": "some_static_agent"}` |
| **期望** | `generate_recommended_questions` 被调用（`reco_task` 非 None） |

#### TC-11 — loader 降级：无 AgentConfig loader 时使用 `_shared_loader`

| 项 | 内容 |
|----|------|
| **前置条件** | 所有 AgentConfig 的 `extra["loader"]` 均为 None；`self._shared_loader` 已在 `start_heartbeat` 中赋值 |
| **期望** | `_build_graph` 接收到 `loader=self._shared_loader`（非 None）；无异常 |

#### TC-12 — loader 三级均不可用时优雅降级

| 项 | 内容 |
|----|------|
| **前置条件** | 所有 AgentConfig 无 loader；`self._shared_loader=None` |
| **期望** | `_build_graph` 接收到 `loader=None`；记录 warning 日志；`process_command` 正常执行不抛出异常 |

#### TC-13 — ResumeCommand 下动态路径兼容

| 项 | 内容 |
|----|------|
| **输入** | `ResumeCommand`，`header_metadata = {"object_ids": ["obj_a"], "thread_id": "t1", "checkpoint_id": "ck1"}` |
| **期望** | `_is_dynamic_agent=True`；cache_key 与首次 AskAgentCommand 相同；命中缓存 graph；`_ensure_agent_config_loaded` 跳过 |

#### TC-14 — cache_key 与资源顺序无关（排序稳定）

| 项 | 内容 |
|----|------|
| **输入 A** | `object_ids=["obj_b", "obj_a"]` |
| **输入 B** | `object_ids=["obj_a", "obj_b"]` |
| **期望** | 两次请求的 `cache_key` 相同（因 fingerprint 基于 `sorted(mounted_objects)`） |
