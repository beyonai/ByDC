# 🐋 ByDC — 企业数据中枢

[![PyPI](https://img.shields.io/pypi/v/by-datacloud?color=blue)](https://pypi.org/project/by-datacloud/) [![Python](https://img.shields.io/badge/python-3.12+-yellow.svg)](https://www.python.org/) [![License](https://img.shields.io/badge/license-Apache_2.0-green.svg)](LICENSE)

**ByDC**（Beyond Data Core）是一个企业数据中枢，为 AI 智能体提供低门槛的数据查询与数据操作能力。

企业数据通常存在数据关系复杂、技术形态多样等特点，不易于被智能体理解；ByDC 通过构建本体语义层，屏蔽底层数据的技术复杂性，让智能体更容易理解和操作数据，从而提升推理效率与准确性。

在部署上，ByDC 与现有生态兼容，无需迁移数据、无需重构业务、无需改造 IT 系统。

在使用上，ByDC 以自然语言为唯一入口：输入问题即可获得结构化数据结果，输入指令即可完成数据操作类 API 的调用。

## Highlights

- **业务本体语义层** — 通过业务对象 + 关系 + 规则构建公司级语义网络，解决数仓只汇总数据、AI 听不懂业务语义的问题；`col_id_002` 变成"客户编号"，大模型真正理解业务含义。
- **零 ETL 联邦查询** — 通过数据虚拟化 + 跨源联邦计算，解决数据散在多个异构数据库、AI 无法跨源分析的问题；数据原地不动，无需搬运，实时跨源查询。
- **异构数据融合（建设中）** — 通过对非结构化文档进行结构化标签增强，建立文档与业务对象的双向关联，解决结构化查询与文档检索割裂、无法联合分析的问题。
- **性能与准确率双保障** — 通过自建 DSL 规则引擎，简单任务优先走规则路径保证响应速度，复杂任务自动降级到 text2SQL 兜底，解决大模型数据查询普遍慢且不稳定的问题。
- **操作安全人工确认（建设中）** — 所有数据操作类 API 在执行前均弹出确认表单，由人工审核后方可执行，解决 AI 自动操作数据存在误操作风险的问题；查询自动执行，操作必须确认，边界清晰。

## 安装

###  方式1：使用安装包

```bash
# 环境要求：Python >= 3.12，uv >= 0.7
pip install by-datacloud
```

总包会直接打入以下源码模块：

- `datacloud-analysis`
- `datacloud-data[all]`
- `datacloud-knowledge`

安装后可直接导入：

```python
import by_datacloud
import datacloud_analysis
import datacloud_data_sdk
import datacloud_knowledge
```

---

### 方式2：使用源码

在ByDC仓库的根目录下执行以下命令

```bash
# 环境要求：Python >= 3.12，uv >= 0.7
uv sync
```



## 快速开始

### demo数据初始化



### 运行示例

`OntologyAgent` 是对外暴露的公开 API，实例应长期持有以充分利用进程级图缓存：

```python
import asyncio
import os
import uuid

from datacloud_analysis.ontology_agent import (
    AnswerEvent, ErrorEvent, InterruptEvent,
    OntologyAgent, OntologyAgentConfig, StepEvent, ThinkingEvent,
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

应用示例

- 示例1：[直接使用本项目](https://github.com/beyonai/ByDC/tree/main/examples/chatbi_demo)
- 示例2：[在byclaw-all中使用本项目](https://github.com/beyonclaw/byclaw-all/tree/main/byclaw-data)

---



## 模块概览

```
用户自然语言
      │
      ▼
┌─────────────────────────────┐
│     datacloud-analysis      │  超级分析智能体：意图识别 → ReAct 推理 → 工具调用 → 响应
└──────────┬──────────────────┘
           │ 依赖
     ┌─────┴──────┐
     ▼            ▼
┌─────────┐  ┌──────────────────┐
│knowledge│  │   datacloud-data │  数据虚拟化：本体加载 → 查询计划 → 跨源执行 → 结果格式化
└─────────┘  └──────────────────┘
术语知识底座
```

| 模块 | 定位 | 核心能力 |
|------|------|----------|
| `datacloud-analysis` | 分析智能体入口，面向 agent 提供数据查询与推理执行能力 | 意图识别、贪心参数抽取、渐进降级执行、澄清对话、会话持久化 |
| `datacloud-data` | 数据虚拟化层，面向本体语言提供跨数据源的统一数据访问 | 本体驱动、同源下沉查询、跨源联邦执行、虚拟动作生成、REST/MCP/GraphQL |
| `datacloud-knowledge` | 知识服务底座，解决自然语言与系统标准术语之间的语义鸿沟 | 字段别名解析、术语检索、查询澄清、澄清回填、术语构建 CLI |

---



## 核心模块

### datacloud-analysis

超级分析智能体（Super Analysis Agent），基于 LangGraph 实现从自然语言到数据洞察的完整主链路。

**设计思想：** 使用前完成本体治理（前置依赖）；运行时在 agent 层**贪心**——在工具调用前尽可能多地识别任务、抽取参数、消除歧义；降级时在工具层**渐进**——从简单到复杂逐级兜底。

核心流程：

```
意图识别 → LLM 多轮推理（ReAct）→ 工具调用（Hook 增强）→ 澄清对话（interrupt）→ 响应格式化
```

主要特性：
- 贪心参数抽取：工具调用前完成字段映射、复杂条件识别，减少 LLM 轮次
- 渐进降级：优先走 DSL 标准路径（text2DSL），遇到复杂条件自动降级到 text2SQL
- 澄清中断：歧义无法自动消解时，`interrupt()` 暂停图执行，等待用户确认后恢复
- 会话持久化：基于 PostgreSQL/OpenGauss Checkpointer，支持跨请求状态恢复
- 流式推送：thinking token 和答案 token 逐 chunk 推送，首字节响应 ≤ 1s

公开 API：

```python
from datacloud_analysis.ontology_agent import OntologyAgent, OntologyAgentConfig

agent = OntologyAgent(OntologyAgentConfig(
    api_key="...", model="...", resource_path="...", sql_execute_url="...",
))
async for event in agent.ask(question="查询本月营收", object_codes=["revenue"]):
    ...
```

详见 [`packages/datacloud-analysis/README.md`](packages/datacloud-analysis/README.md)

---

### datacloud-data

数据虚拟化模块，负责把本体语义语言转化为物理检索或物理操作的数据库语言，并返回执行结果。

**定位：** 面向本体语言提供跨数据源、跨数据服务、跨数据结构的数据虚拟化服务。

- **跨数据源**：允许把两个不同数据源的数据表虚拟成一个本体对象
- **跨数据服务**：允许把 DB 数据库表和 API 虚拟成一个本体视图
- **跨数据结构**：允许把 DB 数据库表和文档虚拟成一个本体对象

查询执行链路：

```
自然语言 → LangGraphPlanGenerator（LLM 生成计划）→ 计划校验
  → Executor 分发（SQL / HTTP API / 虚拟动作）
  → Aggregator（同源下沉 / 跨源联邦合并）
  → 结果格式化（术语值转换 + CSV 溢出导出）
```

公开 API：

```python
from datacloud_data_sdk import InvocationContext, OntologyLoader

loader = OntologyLoader()
loader.load_from_owl_resource_directory(path)
loader.configure(plan_generator=LangGraphPlanGenerator(...), ...)

obj = loader.get_object("sales_bo")
with InvocationContext(tenant_id="t1", user_id="u1"):
    result = await obj.query("查询本月商机列表")
```

详见 [`packages/datacloud-data/README.md`](packages/datacloud-data/README.md)

---

### datacloud-knowledge

知识服务模块，提供术语知识构建、术语查询服务、语义知识推理等能力。

**定位：** 解决"用户怎么说"和"系统怎么懂"之间的语义鸿沟，为上层分析智能体提供稳定的知识底座。

数据模型核心表：`Term`（术语主表）、`TermName`（所有名称/别名）、`TermType`（类型编码）、`TermKnowledge`（关联知识）、`TermRelation`（术语间关系）、`TermVocabulary`（分词词典）。

公开 API：

```python
from datacloud_knowledge.provider import FunctionKnowledgeProvider

provider = FunctionKnowledgeProvider()
analysis = provider.prepare_query_clarification(
    query="查询近三个月高价值客户",
    ontology_code="sales",
    structured_input={...},
    mode="query",
)
```

术语构建 CLI：

```bash
datacloud-knowledge bootstrap ./path/to/package --schema whale_datacloud
```

详见 [`packages/datacloud-knowledge/README.md`](packages/datacloud-knowledge/README.md)

---

## 开发规范

统一遵守根目录规范（根级优先）：

| 规范文档 | 说明 | 优先级 |
|----------|------|--------|
| [`docs/项目规范/CODING_CONVENTIONS.md`](docs/项目规范/CODING_CONVENTIONS.md) | Python 编码规范（全项目通用） | **根级 · 最高** |
| [`docs/项目规范/TESTING_CONVENTIONS.md`](docs/项目规范/TESTING_CONVENTIONS.md) | 测试规范与覆盖率要求 | **根级 · 最高** |

---

## 开发指南



### Monorepo 结构

```text
by_datacloud/
├── pyproject.toml
├── uv.lock
├── README.md
├── docs/
├── src/
├── tests/
├── packages/
│   ├── datacloud-analysis/     # 分析智能体
│   ├── datacloud-data/         # 数据虚拟化
│   ├── datacloud-knowledge/    # 知识服务
│   └── datacloud-memory/       # 会话记忆
└── examples/
    └── chatbi_demo/            # ChatBI 演示工程
```

### Workspace 依赖管理

根 `pyproject.toml` 中通过 `tool.uv.workspace` 管理成员。示例：为 `datacloud-analysis` 添加依赖：

```bash
uv add --package datacloud-analysis <package>
```


```bash
pip install by-datacloud
```

总包会直接打入以下源码模块：

- `datacloud-analysis`
- `datacloud-data[all]`
- `datacloud-knowledge`

安装后可直接导入：

```python
import by_datacloud
import datacloud_analysis
import datacloud_data_sdk
import datacloud_knowledge
```

## 项目结构与核心模块

当前仓库采用 Monorepo，目录分为两层：

- `packages/`：核心 SDK 与基础能力层
- `examples/`：应用样例与演示工程

核心模块如下：

1. `datacloud-analysis`（`packages/datacloud-analysis`）
   - 顶层 AI 分析/编排 SDK（原 `datacloud-agent`）
   - 依赖 `datacloud-data`、`datacloud-knowledge`、`datacloud-memory`

2. `datacloud-data`（`packages/datacloud-data`）
   - 核心数据查询与执行 SDK
   - 提供 NL2Data、异构数据源接入、执行链路能力

3. `datacloud-knowledge`（`packages/datacloud-knowledge`）
   - 领域知识、本体、术语检索与约束能力

4. `datacloud-memory`（`packages/datacloud-memory`）
   - 会话级与跨会话记忆存储、检索与压缩能力

5. `sales_analysis_demo`（`examples/sales_analysis_demo`）
   - 业务样例工程（`frontend/`、`backend/`、`mock_env/`）
   - `backend/datacloud_data_service/` 为数据服务层示例实现

## 开发规范

统一遵守根目录规范（根级优先）：

| 规范文档 | 说明 | 优先级 |
|----------|------|--------|
| [`docs/项目规范/CODING_CONVENTIONS.md`](docs/项目规范/CODING_CONVENTIONS.md) | Python 编码规范（全项目通用） | **根级 · 最高** |
| [`docs/项目规范/TESTING_CONVENTIONS.md`](docs/项目规范/TESTING_CONVENTIONS.md) | 测试规范与覆盖率要求 | **根级 · 最高** |

