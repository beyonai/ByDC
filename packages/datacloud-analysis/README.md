# datacloud-analysis

超级分析智能体（Super Analysis Agent）是 dataCloud 2.0 的核心智能体服务，基于 LangGraph 实现从自然语言到数据洞察的完整主链路。

## 核心定位

**中枢大脑**：接收用户自然语言查询，通过意图识别、知识增强、多轮 ReAct 推理、工具调用和结果格式化，完成从问题到数据的完整闭环。

---

## 目录

- [项目结构](#项目结构)
- [图拓扑](#图拓扑)
  - [V0.4 图（当前默认）](#v04-图当前推荐)
  - [V0.3 图（Legacy）](#v03-图legacy)
- [核心模块说明](#核心模块说明)
- [状态定义](#状态定义-agentstate)
- [流式推送体系](#流式推送体系)
- [中断与恢复](#中断与恢复)
- [Hook 插件系统](#hook-插件系统)
- [配置项](#配置项)
- [快速开始](#快速开始)
- [测试](#测试)

---

## 项目结构

```
packages/datacloud-analysis/
├── src/datacloud_analysis/
│   ├── agent.py                        # 对外工厂函数 create_agent()
│   ├── bootstrap.py                    # SDK 初始化（DB / Checkpointer）
│   ├── logging_setup.py
│   ├── config/
│   │   ├── env.py                      # 环境变量定义（Pydantic Settings）
│   │   └── db_url.py                   # 数据库连接字符串构建
│   ├── orchestration/                  # ★ LangGraph 编排核心
│   │   ├── state.py                    # AgentState 状态定义
│   │   ├── graph_builder.py            # 图构建入口（V0.3 / V0.4 双路径）
│   │   ├── graph_compile_policy.py     # 编译策略（强制 checkpointer）
│   │   ├── runner.py                   # run_agent() 流式执行入口
│   │   ├── message_util.py             # 消息辅助工具
│   │   ├── intend/
│   │   │   ├── node.py                 # 意图识别节点
│   │   │   └── command_router.py       # 命令插件路由
│   │   ├── execution/
│   │   │   ├── llm_call_node.py        # LLM 调用节点（Prompt Caching）
│   │   │   ├── hook_aware_tool_node.py # ★ V0.4 工具节点（含 Hook 钩子）
│   │   │   ├── react_loop.py           # V0.3 ReAct 主循环（兼容保留）
│   │   │   ├── finish_react_node.py    # finish_react 参数提取节点
│   │   │   ├── llm_retry.py            # LLM 重试与备用模型策略
│   │   │   ├── llm_checkpoint.py       # LLM 失败断点恢复
│   │   │   ├── make_tool_node.py       # per-tool 节点工厂（V0.3）
│   │   │   ├── tool_dispatcher_node.py # 工具调度兜底（V0.3）
│   │   │   └── tool_wrapper.py         # 工具调用包装
│   │   ├── clarification/
│   │   │   ├── analyze_clarify_node.py # 澄清需求分析节点
│   │   │   └── user_clarify_node.py    # 用户交互澄清节点（含 interrupt）
│   │   ├── respond/
│   │   │   ├── node.py                 # 最终响应节点
│   │   │   └── formatter.py            # 结果序列化与分块推送
│   │   └── shared/
│   │       ├── contracts.py            # PlanTask / TaskResult / ArtifactRef
│   │       ├── model_resolver.py
│   │       └── query_shape_utils.py
│   ├── clarification/                  # 澄清 SDK 调用层
│   ├── command_plugins/                # 命令插件（文件分页、术语更新等）
│   ├── i18n/
│   │   └── prompts.py                  # 多语言系统提示词
│   ├── session/
│   │   ├── checkpointer.py             # Checkpointer 单例管理
│   │   └── pg_opengauss.py             # OpenGauss/PostgreSQL Saver 工厂
│   ├── tool_hook_plugins/              # ★ 工具 Hook 插件系统
│   │   ├── manager.py                  # HookPluginManager
│   │   ├── types.py                    # HookContext / ClarificationNeededError
│   │   └── builtin/
│   │       ├── query_clarification_plugin.py  # 查询澄清插件
│   │       └── semantic_param_enhancer.py     # 语义参数增强插件
│   ├── tools/
│   │   ├── ask_user.py                 # 人工确认工具
│   │   ├── file_io.py                  # 文件 I/O 工具
│   │   ├── knowledge.py                # 知识检索工具
│   │   └── ontology_tool_loader.py     # 本体工具动态生成
│   └── workspace/
│       └── runtime.py                  # 工作目录解析
└── tests/dca/
    ├── unit/                           # 单元测试
    └── integration/                    # 集成测试（含 DB 测试）
```

---

## 图拓扑

图的构建入口为 `orchestration/graph_builder.py`，通过环境变量 `DATACLOUD_USE_PREBUILT_REACT` 选择执行路径。

### V0.4 图（当前推荐）

> 设置 `DATACLOUD_USE_PREBUILT_REACT=true` 启用。

使用 LangGraph prebuilt `ToolNode` + `HookAwareToolNode` 封装，结构更清晰，澄清流程内聚在 tools 节点内。

```
START
  │
  ▼
┌─────────────┐
│ intend_node │  意图识别：命令路由 vs ReAct
└──────┬──────┘
       │ intent=command          │ intent=react
       ▼                         ▼
      END              ┌─────────────────┐
                       │  agent (llm_call)│  LLM 多轮推理 + 流式推送
                       └────────┬────────┘
                                │ tool_calls 存在
                    ┌───────────┴───────────┐
                    │ tools (HookAwareToolNode)│
                    │  ├ run_before (Hook)      │  参数增强 / 澄清检测
                    │  ├ ToolNode.ainvoke       │  实际工具执行
                    │  └ run_after  (Hook)      │  结果审计
                    └──┬────────────┬──────────┘
                       │            │
              finish_react      ClarificationNeededError
                       │            │
                       ▼            ▼
            ┌──────────────┐  ┌──────────────────┐
            │finish_react  │  │ analyze_clarify   │  快速路径复用 paradigm_list
            │_node         │  └────────┬─────────┘
            └──────┬───────┘           │
                   │            ┌──────▼──────────┐
                   │            │  user_clarify   │  interrupt() 等待用户
                   │            │  _node          │  Command(resume=...) 继续
                   │            └──────┬──────────┘
                   │                   │ 回写 clarification_formatted_params
                   │                   └──────────→ tools（重新执行）
                   │
                   ▼
          ┌────────────────┐
          │  respond_node  │  格式化 + 分块推送
          └───────┬────────┘
                  ▼
                 END
```

**路由规则：**

| 路由点 | 条件 | 目标节点 |
|--------|------|----------|
| `after intend` | `execution_status == "command_done"` | `END` |
| `after intend` | 其他 | `agent` |
| `after agent` | 最后 AIMessage 无 `tool_calls` | `respond` |
| `after agent` | `react_round_idx >= max_rounds` | `respond` |
| `after agent` | 有 `tool_calls` | `tools` |
| `after tools` | 检测到 `finish_react` 工具 | `finish_react_node` |
| `after tools` | `ClarificationNeededError` | `analyze_clarify` |
| `after tools` | 其他 | `agent` |
| `after finish_react_node` | 始终 | `respond` |
| `after analyze_clarify` | 始终 | `user_clarify` |
| `after user_clarify` | resume 后 | `tools` |

---

### V0.3 图（Legacy）

> `DATACLOUD_USE_PREBUILT_REACT` 未设置或为 `false` 时使用。

每个工具独立注册为图节点，支持 Send API 并行工具执行。

```
START
  │
  ▼
┌─────────────┐
│ intend_node │
└──────┬──────┘
       │ react
       ▼
┌──────────────┐
│  llm_call    │  _invoke_llm_with_fallback（主模型 + 备用 + 断点恢复）
└──────┬───────┘
       │ tool_calls
       │ Send([tool_name, ...])       ← 并行分发
       ▼
┌──────────────────────────────────────┐
│  per-tool nodes（每工具独立节点）     │
│  make_tool_node() + hook 包装        │
└──────────────┬───────────────────────┘
               │
    ┌──────────┴──────────┐
    │                     │
  工具执行完成        ClarificationNeededError
    │                     │
    ▼                     ▼
┌─────────┐       ┌──────────────────┐
│llm_call │       │ analyze_clarify  │
│（下一轮）│       └────────┬─────────┘
└─────────┘                │
                    ┌──────▼──────────┐
                    │  user_clarify   │
                    └──────┬──────────┘
                           │ resume
                           └──→ per-tool nodes（重新执行）

       ...（循环直到 finish_react）...

  finish_react 检测
       │
       ▼
┌──────────────┐
│ respond_node │
└──────────────┘
       │
      END
```

---

## 核心模块说明

### `agent.py` — 对外工厂

```python
from datacloud_analysis.agent import create_agent

graph = create_agent(
    tools={"query_revenue": revenue_tool},      # 外部工具注入
    mounted_objects=["ontology_code"],           # 本体工具动态生成
    system_prompt_override="...",               # 可选：覆盖系统提示词
)
compiled = compile_graph_with_policy(graph, caller_name="my_app")
```

`create_agent()` 完成：
- 合并内置工具（`finish_react` 哨兵、`ask_user`、`file_io`）
- 通过 `ontology_tool_loader` 动态生成本体工具
- 注入 `inject_query_fields` schema 补丁
- 调用 `build_analysis_graph()` 按路径构建图

---

### `orchestration/intend/node.py` — 意图识别

```python
async def intend_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]: ...
```

1. 提取最后一条用户消息
2. 调用 `CommandRouter.try_dispatch()` 匹配命令插件
3. 命令匹配 → `{"intent": "command", "execution_status": "command_done"}`
4. 未匹配 → `{"intent": "react", "execution_status": "execution"}`

---

### `orchestration/execution/llm_call_node.py` — LLM 调用节点

```python
def make_llm_call_node(...) -> Callable: ...
```

- 每轮读取完整 `state["messages"]` 作为对话历史
- 系统提示词支持 **Prompt Caching**（Anthropic `cache_control`）
- 动态注入知识片段（`knowledge_snippets`）和术语提示（`term_hints`）
- 流式调用：推送 thinking token（`REASONING_LOG_DELTA`）+ 答案（`ANSWER_DELTA`）
- 三层容错：主模型 → 备用模型 → Redis 断点保存

---

### `orchestration/execution/hook_aware_tool_node.py` — V0.4 工具节点 ★

```python
class HookAwareToolNode(ToolNode):
    async def ainvoke(self, state: Any, config: RunnableConfig) -> dict[str, Any]: ...
```

执行流程：

```
1. 提取 AIMessage.tool_calls
2. for each tool_call:
   a. 构建 HookContext（工具名、原始参数、状态快照）
   b. hook_manager.run_before(ctx)
      → 参数增强（语义 + 澄清回填）
      → ClarificationNeededError → Command(goto="analyze_clarify")
   c. 以增强后的参数替换原 tool_call
3. super().ainvoke()  ← prebuilt ToolNode 实际执行
4. for each ToolMessage:
   hook_manager.run_after(ctx)
5. 检测 query_data block → 写入 react_last_query_data
```

---

### `orchestration/execution/react_loop.py` — V0.3 ReAct 主循环

> V0.3 路径使用，V0.4 中不再作为主流程入口，保留兼容。

核心能力：

- **流式 LLM 调用**：`_stream_llm_call()` 逐 chunk 推送 thinking / answer token
- **工具并发执行**：通过 Send API 将多个 tool_call 分发到各自节点
- **finish_react 哨兵**：LLM 通过调用 `finish_react` 工具主动结束循环
- **上下文压缩**：`_compress_tool_result()` 裁剪超长工具返回，保护 context window
- **中断恢复**：检测 `GraphBubbleUp`，序列化 `react_messages` 到 state
- **LLM 断点**：失败时保存到 Redis，下次恢复继续

---

### `orchestration/clarification/` — 澄清子流程

| 节点 | 文件 | 说明 |
|------|------|------|
| `analyze_clarify` | `analyze_clarify_node.py` | 解析 `ClarificationNeededError`，复用 `paradigm_list` 快速路径（跳过 SDK 调用，节省 15–22s） |
| `user_clarify` | `user_clarify_node.py` | `interrupt()` 暂停等待用户选择，`Command(resume=...)` 后写入 `clarification_formatted_params` 并路由回 tools |

---

### `orchestration/respond/` — 响应格式化

`respond_node` → `format_result()` 按 `result_type` 分支处理：

| result_type | 处理逻辑 |
|-------------|----------|
| `text` | 直接推送文本（若未流式推送则补发） |
| `query_result` | 从 `react_last_query_data` 读取，分块推送（每 100 行）|
| `csv_file` | 文件路径推送 |
| `json` | JSON 序列化推送 |

---

## 状态定义（AgentState）

`orchestration/state.py` 定义，继承自 `MessagesState`（LangGraph 内置）。

| 分类 | 关键字段 | 说明 |
|------|----------|------|
| **消息历史** | `messages` | 完整对话消息列表（MessagesState 内置） |
| **请求上下文** | `agent_id`, `agent_name`, `workspace_dir` | 调用方身份和工作目录 |
| **查询上下文** | `user_query`, `enriched_query`, `knowledge_snippets`, `term_hints` | 原始问题及知识增强结果 |
| **意图路由** | `intent`, `clarify_needed`, `query_mode`, `target_tool` | 意图识别结果 |
| **执行运行时** | `execution_status`, `react_round_idx`, `react_final`, `answer_streamed` | 执行进度和结果 |
| **澄清状态** | `pending_clarification_context`, `clarification_analyze_result`, `clarification_formatted_params` | 澄清全生命周期数据 |
| **中断/恢复** | `react_messages`, `react_pending_tool_calls`, `react_checkpoint`, `react_last_query_data` | 跨实例恢复所需数据 |
| **多任务** | `planned_tasks`, `task_queue`, `results_list`, `results_map` | 并行任务规划与聚合 |
| **结果** | `final_answer`, `artifact_refs`, `final_summary` | 最终输出 |

---

## 流式推送体系

所有推送均通过 `gateway_context`（由 `config["configurable"]["gateway_context"]` 注入）。

| 事件类型 | 触发时机 | 数据内容 |
|----------|----------|----------|
| `REASONING_LOG_DELTA` | LLM 输出 thinking block 时 | 思考文本片段（逐 chunk） |
| `ANSWER_DELTA` | LLM 推理出 `finish_react.answer` 参数时 | 答案文本片段（逐 chunk） |
| `ANSWER_DELTA` | `respond_node` 推送表格数据时 | 分块表格行（每 100 行） |

> thinking token 推送函数：`react_loop._emit_thinking_token()`
> 支持 Anthropic 增量式 thinking block 和 MiniMax 累积式识别。

---

## 中断与恢复

### 澄清中断（主路径）

```
工具执行 → Hook.run_before() 检测 → ClarificationNeededError
  → HookAwareToolNode 捕获 → Command(goto="analyze_clarify")
  → analyze_clarify_node（解析 paradigm）
  → user_clarify_node → interrupt()   ← 图暂停，状态落库
  → 用户回复 → Command(resume=user_reply)
  → user_clarify_node 写入 clarification_formatted_params
  → 路由回 tools，Hook.run_before() 读取 clarification_formatted_params 回填参数
```

### LLM 失败断点恢复（可选）

当主模型和备用模型均不可用时：
1. 将当前 `messages` + `round_idx` 序列化保存至 Redis
2. 向用户推送引导文案
3. 下次请求时检测断点 → 自动恢复继续

---

## Hook 插件系统

`tool_hook_plugins/` 提供可插拔的工具前后钩子。

```python
class HookPluginManager:
    async def run_before(ctx: HookContext) -> tuple[HookContext, None]: ...
    async def run_after(ctx: HookContext) -> tuple[HookContext, None]: ...
```

**内置插件：**

| 插件 | 触发条件 | 作用 |
|------|----------|------|
| `QueryClarificationPlugin` | 工具调用前 | 检测查询歧义，抛 `ClarificationNeededError` 触发澄清流程 |
| `SemanticParamEnhancer` | 工具调用前 | 语义增强工具参数（术语翻译、字段映射） |

**自定义插件：**

```python
from datacloud_analysis.tool_hook_plugins.types import HookContext, HookSignalError

class MyPlugin:
    async def run_before(self, ctx: HookContext) -> tuple[HookContext, None]:
        # 修改 ctx["tool_args"] 进行参数增强
        return ctx, None
```

---

## 配置项

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `DATACLOUD_USE_PREBUILT_REACT` | `false` | `true` 启用 V0.4 图路径 |
| `DATACLOUD_DB_HOST` | — | OpenGauss 数据库主机 |
| `DATACLOUD_DB_DATABASE` | — | 数据库名 |
| `DATACLOUD_DB_USER` | — | 数据库用户名 |
| `DATACLOUD_DB_PASSWORD` | — | 数据库密码 |
| `DATACLOUD_DB_PORT` | `5432` | 数据库端口 |
| `DATACLOUD_LLM_MODEL` | — | 主 LLM 模型 ID |
| `DATACLOUD_LLM_FALLBACK_MODEL` | — | 备用 LLM 模型 ID |
| `DATACLOUD_MAX_REACT_ROUNDS` | `10` | ReAct 最大轮数 |
| `DATACLOUD_LLM_TEMPERATURE` | `0` | LLM 温度参数 |

---

## 快速开始

### 安装

```bash
uv sync
```

### 初始化并运行

```python
import asyncio
from datacloud_analysis import bootstrap
from datacloud_analysis.agent import create_agent
from datacloud_analysis.orchestration.graph_compile_policy import compile_graph_with_policy

async def main():
    # 1. 初始化（数据库连接、Checkpointer）
    await bootstrap.setup()

    # 2. 构建图（V0.4 路径）
    import os
    os.environ["DATACLOUD_USE_PREBUILT_REACT"] = "true"

    graph = create_agent(tools={"my_tool": my_tool})
    compiled = compile_graph_with_policy(graph, caller_name="demo")

    # 3. 执行
    config = {"configurable": {"thread_id": "session-001"}}
    result = await compiled.ainvoke(
        {"messages": [{"role": "user", "content": "查询本月营收"}]},
        config,
    )

    await bootstrap.teardown()

asyncio.run(main())
```

---

## 测试

```bash
# 全部单元测试
uv run pytest tests/dca/unit/ -v

# 流式 thinking token 集成测试（mock-based，无需 DB）
uv run pytest tests/dca/integration/test_thinking_token_stream.py -v

# 中断/恢复集成测试（需要真实 OpenGauss 环境）
uv run pytest tests/dca/integration/test_interrupt_resume_prebuilt.py -v -m db_integration

# 带覆盖率
uv run pytest --cov=datacloud_analysis --cov-report=term-missing
```

**测试标记说明：**

| 标记 | 说明 |
|------|------|
| `db_integration` | 需要真实 OpenGauss 连接，默认跳过 |
| `asyncio` | 异步测试（`pytest-asyncio` 自动处理） |
