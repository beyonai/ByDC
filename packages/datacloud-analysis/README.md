# datacloud-analysis

---

## 简介

`datacloud-analysis` 是 dataCloud 平台的agent入口，负责将用户的自然语言问题转化为结构化数据查询或数据操作，并返回结果。

## 定位

面向【agent】提供低门槛的【数据查询】、【数据操作】的【推理及执行】能力。



## 设计思想

为兼顾数据服务的性能及准确率，整个设计基于【本体治理】框架，在推理时，使用了【分类】、【贪心】、【渐进】的设计思想。

### 前置依赖

本框架运行依赖以下本体治理工作，需在正式使用前完成。

1. **术语治理**：梳理字典术语、列表术语及已知同义词，供歧义识别阶段做规则匹配。
2. **本体治理**：将 API 或数据库表建设为本体对象/本体视图。本体属性需绑定字典术语或列表术语，并细分为维度、度量两大类型。

### 分类思想

本框架对数据读取、任务复杂度、本体属性进行了标准化分类，框架运行逻辑基于此分类体系展开。

**1、数据读取任务分类**：数据读取分为查询和统计两类，分别对应 `query_*`、`compute_*` 两类工具。

**2、任务复杂度分类**：分为标准任务和定制任务。定制任务通过 `complex_conditions` 参数识别，当前实现了"查询条件跨对象"一种类型，后续可扩展更多类型。

**3、本体属性分类**：对象属性分为维度（DIMENSION）和度量（MEASURE）两大类，每类细分若干子类，不同子类在分组、条件过滤、统计函数上有不同规则约束。

| 属性类型 | 属性子类 | 子类编码          | 分组规则                                  | 统计函数规则                          |
| -------- | -------- | ----------------- | ----------------------------------------- | ------------------------------------- |
| 维度     | ID       | `id`              | 仅支持按自身分组                          | —                                     |
| 维度     | 名称     | `name`            | 仅支持按自身分组                          | —                                     |
| 维度     | 时间     | `datetime`        | 支持时间粒度函数：DATE/MONTH/YEAR/QUARTER | —                                     |
| 维度     | 账期     | `period`          | 支持时间粒度函数：DATE/MONTH/YEAR/QUARTER | —                                     |
| 维度     | 数值     | `numeric`         | —                                         | —                                     |
| 维度     | 描述     | `description`     | —                                         | —                                     |
| 维度     | 虚拟标签 | `virtual_tag`     | 仅支持按自身分组                          | —                                     |
| 度量     | 主键     | `primary_key`     | 仅支持按自身分组                          | COUNT()                               |
| 度量     | 普通数值 | `raw_number`      | 支持 RANGE 范围分组                       | SUM/AVG/MAX/MIN/TOPN/MEDIAN           |
| 度量     | 普通指标 | `basic_metric`    | 支持 RANGE 范围分组                       | SUM/AVG/MAX/MIN/TOPN/MEDIAN           |
| 度量     | 拍照指标 | `snapshot_metric` | 支持 RANGE 范围分组                       | MAX/MIN/TOPN/MEDIAN（跨账期不可 SUM） |
| 度量     | 派生指标 | `derived_metric`  | 支持 RANGE 范围分组                       | —（比率类，不可二次聚合）             |
| 度量     | 指标公式 | `formula_metric`  | 支持 RANGE 范围分组                       | SUM/AVG/MAX/MIN/TOPN/MEDIAN           |

RANGE 分组函数格式：`RANGE(字段, 开始值, 结束值, '标签')`，例如 `RANGE(年龄, 0, 18, '未成年')`。

### 贪心思想

利用 agent 的 ReAct & function call 机制，在工具调用**前**尽可能完成任务识别和参数抽取，减少工具调用轮次。

| 任务                       | 决策内容                                                     | 输出                                       |
| -------------------------- | ------------------------------------------------------------ | ------------------------------------------ |
| 选工具（本体）             | 根据工具描述中的字段能力表，确定目标对象/视图                | 确定工具名前缀 `{code}`                    |
| 选工具（任务分类）         | 确定意图：查明细 or 做统计                                   | 工具名：`query_{code}` 或 `compute_{code}` |
| 参数抽取（标准参数）       | 从自然语言抽取结构化参数（select、filters、order_by 等）     | 输出 tool_params                           |
| 参数抽取（字段映射）       | 对照字段能力表做直接匹配：命中则取编码或名称；**无法直接推理时，原词写入参数，禁止猜测替换** | 命中写 field_code；未命中写用户原词        |
| 参数抽取（复杂子条件识别） | 识别过滤值无法在填参时确定为字面常量的条件（相对排名、跨对象子查询、动态比较值），写入 `complex_conditions` | 触发 text2SQL 路径                         |

**字段映射原则**：LLM 在填写 `select` / `filters.field` / `order_by.field` 时，直接对照工具描述里的字段能力表进行匹配。能直接命中则取表中的编码或名称；无法直接推理出对应字段时，保留用户原词写入，**禁止猜测性地替换为已有字段**。

> 示例：用户说"查询物理网格数据，包含网格编码、网格名称、贡献率三个字段"。字段能力表中有"网格编码"和"网格名称"，直接命中；"贡献率"不在表中，不得强行替换为已有字段，直接原词写入：
>
> ```json
> {
> "select": ["网格编码", "网格名称", "贡献率"],
> "filters": [{ "field": "贡献率", "op": "gt", "value": 100 }]
> }
> ```
>
> 渐进阶段再对"贡献率"做规则修正或触发 interrupt 追问用户。

**复杂子条件识别原则**：`complex_conditions` 只收过滤**值**在填参时无法确定为字面常量的那部分条件，包括：①相对排名（"后30%"、"前N名"）；②跨对象子查询；③动态比较值（"高于行业平均"）。其余可字面化的条件仍按正常参数填写。

### 渐进思想

贪心阶段识别出任务类型和参数后，渐进思想决定工具层如何降级执行——优先走简单路径，能自动处理则自动，不能处理则逐级升级。

**1、任务复杂渐进**：优先引导 LLM 使用 `query_{code}` / `compute_{code}` 标准工具，规则转 DSL；若包含 `complex_conditions` 参数，则路由到 `data_query_{code}`，走 text2SQL。

**2、意图澄清渐进**（数据查询场景）：

- 先通过规则进行歧义意图判断（标准术语 + 术语同义词）
- 能自动修正尽量自动修正：
  - 能局部修正则局部修正（如 select 有歧义只修正 select）
  - 无法局部修正则整体修正（重新调整 select、from、where）
- 无法自动修正时，列出可能选项，触发 interrupt 让用户确认后继续执行

---



## 快速开始

### 安装

```bash
uv sync
```

### 发起问答

`OntologyAgent` 是对外暴露的公开 API，无需关心底层图构建细节。实例应长期持有（如应用启动时创建一次），以充分利用进程级图缓存。

```python
import asyncio
import os
import uuid

from datacloud_analysis.ontology_agent import (
    AnswerEvent,
    ErrorEvent,
    InterruptEvent,
    OntologyAgent,
    OntologyAgentConfig,
    StepEvent,
    ThinkingEvent,
)

async def main() -> None:
    config = OntologyAgentConfig(
        api_key=os.environ["DEMO_API_KEY"],
        model=os.environ["DEMO_MODEL"],
        base_url=os.environ["DEMO_BASE_URL"],
        resource_path=os.environ["DEMO_RESOURCE_PATH"],
        temperature=float(os.environ["DEMO_TEMPERATURE"]),
        sql_execute_url=os.environ["DEMO_SQL_EXECUTE_URL"],
    )
    agent = OntologyAgent(config)
    thread_id = str(uuid.uuid4())

    async for event in agent.ask(
        question="查询前3条客户清单数据",
        object_codes=["by_customer"],
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
                print("\n[需要澄清，调用 agent.resume() 继续]")

asyncio.run(main())
```

收到 `InterruptEvent` 时，调用 `agent.resume()` 传入用户回复继续执行：

```python
from datacloud_analysis.ontology_agent import ParadigmAnswer, ParadigmGroupSelection, ParadigmOption

async for event in agent.resume(
    thread_id=thread_id,
    object_codes=["by_customer"],
    user_input=ParadigmAnswer(
        selections=[
            ParadigmGroupSelection(
                paradigm_id="field_xxx",
                paradigm_name="字段名称",
                chosen_options=[ParadigmOption(choice_keyword="选项A", recall="recall_value")],
            )
        ]
    ),
):
    ...
```

完整示例见 `examples/chatbi_demo/`。

---

### 配置说明

所有配置通过环境变量注入，定义在 `config/env.py`（Pydantic Settings）。

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `DATACLOUD_USE_PREBUILT_REACT` | `false` | `true` 启用当前推荐图路径 |
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

## 架构设计

### 项目结构

```
packages/datacloud-analysis/
├── src/datacloud_analysis/
│   ├── agent.py                        # 对外工厂函数 create_agent()
│   ├── bootstrap.py                    # SDK 初始化（DB / Checkpointer）
│   ├── logging_setup.py
│   ├── config/
│   │   ├── env.py                      # 环境变量定义（Pydantic Settings）
│   │   └── db_url.py                   # 数据库连接字符串构建
│   ├── orchestration/                  # LangGraph 编排核心
│   │   ├── state.py                    # AgentState 状态定义
│   │   ├── graph_builder.py            # 图构建入口
│   │   ├── graph_compile_policy.py     # 编译策略（强制 checkpointer）
│   │   ├── runner.py                   # run_agent() 流式执行入口
│   │   ├── message_util.py             # 消息辅助工具
│   │   ├── intend/
│   │   │   ├── node.py                 # 意图识别节点
│   │   │   └── command_router.py       # 命令插件路由
│   │   ├── execution/
│   │   │   ├── llm_call_node.py        # LLM 调用节点（Prompt Caching）
│   │   │   ├── hook_aware_tool_node.py # 工具节点（含 Hook 钩子）
│   │   │   ├── react_loop.py           # ReAct 主循环（兼容保留）
│   │   │   ├── finish_react_node.py    # finish_react 参数提取节点
│   │   │   ├── llm_retry.py            # LLM 重试与备用模型策略
│   │   │   └── llm_checkpoint.py       # LLM 失败断点恢复
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
│   ├── command_plugins/                # 命令插件（文件分页、术语更新等）
│   ├── i18n/
│   │   └── prompts.py                  # 多语言系统提示词
│   ├── session/
│   │   ├── checkpointer.py             # Checkpointer 单例管理
│   │   └── pg_opengauss.py             # OpenGauss/PostgreSQL Saver 工厂
│   ├── tool_hook_plugins/              # 工具 Hook 插件系统
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

### 图拓扑

图的构建入口为 `orchestration/graph_builder.py`，通过环境变量 `DATACLOUD_USE_PREBUILT_REACT` 选择执行路径。

#### 当前推荐路径（DATACLOUD_USE_PREBUILT_REACT=true）

使用 LangGraph prebuilt `ToolNode` + `HookAwareToolNode` 封装，澄清流程内聚在 tools 节点内，结构清晰。

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
                    ┌───────────┴────────────┐
                    │ tools (HookAwareToolNode)│
                    │  ├ run_before (Hook)      │  参数增强 / 澄清检测
                    │  ├ ToolNode.ainvoke       │  实际工具执行
                    │  └ run_after  (Hook)      │  结果审计
                    └──┬─────────────┬─────────┘
                       │             │
              finish_react      ClarificationNeededError
                       │             │
                       ▼             ▼
            ┌──────────────┐  ┌──────────────────┐
            │finish_react  │  │ analyze_clarify   │  复用 paradigm_list 快速路径
            │_node         │  └────────┬──────────┘
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

路由规则：

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

#### 兼容路径（DATACLOUD_USE_PREBUILT_REACT=false，默认）

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
│  llm_call    │  主模型 + 备用模型 + 断点恢复
└──────┬───────┘
       │ tool_calls → Send([tool_name, ...])  并行分发
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

### 核心模块说明

#### `agent.py` — 对外工厂

```python
from datacloud_analysis.agent import create_agent

graph = create_agent(
    tools={"query_revenue": revenue_tool},      # 外部工具注入
    mounted_objects=["ontology_code"],           # 本体工具动态生成
    system_prompt_override="...",               # 可选：覆盖系统提示词
)
compiled = compile_graph_with_policy(graph, caller_name="my_app")
```

#### `orchestration/state.py` — AgentState

继承自 LangGraph `MessagesState`，关键字段分类：

| 分类 | 关键字段 | 说明 |
|------|----------|------|
| 消息历史 | `messages` | 完整对话消息列表 |
| 请求上下文 | `agent_id`, `workspace_dir` | 调用方身份和工作目录 |
| 查询上下文 | `user_query`, `knowledge_snippets`, `term_hints` | 原始问题及知识增强结果 |
| 意图路由 | `intent`, `clarify_needed`, `query_mode` | 意图识别结果 |
| 执行运行时 | `execution_status`, `react_round_idx`, `answer_streamed` | 执行进度 |
| 澄清状态 | `pending_clarification_context`, `clarification_formatted_params` | 澄清全生命周期数据 |
| 中断/恢复 | `react_messages`, `react_pending_tool_calls`, `react_checkpoint` | 跨实例恢复所需数据 |
| 结果 | `final_answer`, `artifact_refs`, `final_summary` | 最终输出 |

#### `orchestration/execution/llm_call_node.py` — LLM 调用节点

- 系统提示词支持 Prompt Caching（Anthropic `cache_control`）
- 动态注入知识片段（`knowledge_snippets`）和术语提示（`term_hints`）
- 流式调用：推送 thinking token（`REASONING_LOG_DELTA`）+ 答案（`ANSWER_DELTA`）
- 三层容错：主模型 → 备用模型 → Redis 断点保存

#### `orchestration/execution/hook_aware_tool_node.py` — 工具节点

```
1. 提取 AIMessage.tool_calls
2. for each tool_call:
   a. 构建 HookContext（工具名、原始参数、状态快照）
   b. hook_manager.run_before(ctx)
      → 参数增强（语义 + 澄清回填）
      → ClarificationNeededError → Command(goto="analyze_clarify")
   c. 以增强后的参数替换原 tool_call
3. super().ainvoke()  ← prebuilt ToolNode 实际执行
4. for each ToolMessage: hook_manager.run_after(ctx)
5. 检测 query_data block → 写入 react_last_query_data
```

#### `orchestration/respond/` — 响应格式化

`respond_node` → `format_result()` 按 `result_type` 分支处理：

| result_type | 处理逻辑 |
|-------------|----------|
| `text` | 直接推送文本（若未流式推送则补发） |
| `query_result` | 从 `react_last_query_data` 读取，分块推送（每 100 行）|
| `csv_file` | 文件路径推送 |
| `json` | JSON 序列化推送 |

---
### 中断与恢复

#### 澄清中断（主路径）

当工具参数存在歧义且无法自动消解时，框架通过 LangGraph `interrupt()` 机制暂停图执行，等待用户确认后恢复。

```
工具执行 → Hook.run_before() 检测歧义 → 抛出 ClarificationNeededError
  → HookAwareToolNode 捕获 → Command(goto="analyze_clarify")
  → analyze_clarify_node（解析 paradigm，复用快速路径，节省 15–22s）
  → user_clarify_node → interrupt()        ← 图暂停，状态落库（PostgreSQL）
  → 用户回复 → Command(resume=user_reply)
  → user_clarify_node 写入 clarification_formatted_params
  → 路由回 tools，Hook.run_before() 读取 clarification_formatted_params 回填参数
  → 工具以修正后的参数重新执行
```

关键点：
- `interrupt()` 后图状态完整持久化到 PostgreSQL，进程重启不丢失
- `analyze_clarify_node` 复用 `paradigm_list` 快速路径，跳过 SDK 调用，节省 15–22s
- 澄清回填通过 `clarification_formatted_params` 字段传递，Hook 层透明处理，工具本身无感知

#### LLM 失败断点恢复（可选）

当主模型和备用模型均不可用时：

1. 将当前 `messages` + `round_idx` 序列化保存至 Redis
2. 向用户推送引导文案
3. 下次请求时检测断点 → 自动恢复继续，无需用户重新输入

---

#### 扩展开发

## 插件与扩展

### Hook 插件系统

`tool_hook_plugins/` 提供可插拔的工具前后钩子，在工具执行前后注入自定义逻辑。

```python
class HookPluginManager:
    async def run_before(ctx: HookContext) -> tuple[HookContext, None]: ...
    async def run_after(ctx: HookContext) -> tuple[HookContext, None]: ...
```

内置插件：

| 插件 | 触发时机 | 作用 |
|------|----------|------|
| `QueryClarificationPlugin` | 工具调用前 | 检测查询歧义，抛 `ClarificationNeededError` 触发澄清流程 |
| `SemanticParamEnhancer` | 工具调用前 | 语义增强工具参数（术语翻译、字段映射） |

自定义插件示例：

```python
from datacloud_analysis.tool_hook_plugins.types import HookContext

class MyPlugin:
    async def run_before(self, ctx: HookContext) -> tuple[HookContext, None]:
        # 修改 ctx["tool_args"] 进行参数增强
        return ctx, None
```

### 命令插件系统

`command_plugins/` 提供命令型请求的扩展点，通过 `CommandRouter` 在意图识别阶段匹配并直接执行，不进入 ReAct 循环。

内置命令插件：

| 插件 | 说明 |
|------|------|
| `GetFileByPageCommand` | 分页获取文件内容 |
| `UpdateTermsNameCommand` | 更新术语名称 |

自定义命令插件需实现 `command_plugins/types.py` 中定义的接口，并注册到 `CommandPluginManager`。

---

## 开发指南

详细规范见 `docs/模块规范/`：

- `CODING_CONVENTIONS.md` — 编码规范
- `TESTING_CONVENTIONS.md` — 测试规范

关键约定：

- Python >= 3.12，完整类型注解，MyPy strict mode
- 使用 `uv` 管理依赖，`ruff` 格式化 + Lint
- 禁止 `print()`，使用 `logging`；禁止裸 `except`
- 异步优先：所有 I/O 密集操作使用 `async/await`
- 节点函数签名：`async def xxx_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]`

```bash
# 格式化 + Lint
uv run ruff format .
uv run ruff check . --fix

# 类型检查
uv run mypy .
```

---

## 测试

```bash
# 全部单元测试
uv run pytest tests/dca/unit/ -v

# 流式 thinking token 集成测试（无需 DB）
uv run pytest tests/dca/integration/test_thinking_token_stream.py -v

# 中断/恢复集成测试（需要真实 OpenGauss 环境）
uv run pytest tests/dca/integration/test_interrupt_resume_prebuilt.py -v -m db_integration

# 带覆盖率（要求 >= 90%）
uv run pytest --cov=datacloud_analysis --cov-report=term-missing
```

测试标记说明：

| 标记 | 说明 |
|------|------|
| `db_integration` | 需要真实 OpenGauss 连接，默认跳过 |
| `asyncio` | 异步测试（`pytest-asyncio` 自动处理） |
