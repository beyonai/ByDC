# 编码规范 — datacloud-analysis 专项

> **extends**: [`/docs/项目规范/CODING_CONVENTIONS.md`](../../../docs/项目规范/CODING_CONVENTIONS.md)（Monorepo 根规范，优先级更高）
>
> **适用范围**：`datacloud-analysis` 子项目，`src/datacloud_analysis/` 下所有 Python 源码
>
> **说明**：本文档**仅包含 datacloud-analysis 特有内容**，通用编码规范见根文档。

---

## 1. 环境变量命名 — DATACLOUD Group 列表

本模块所有环境变量遵循根规范的 `<PROJECT>_<GROUP>_<KEY>` 命名规则，Group 取值如下：

```
DATACLOUD_<GROUP>_<KEY>

Group 列表：
  PG              → PostgreSQL 连接（checkpoint 存储）
  WORKSPACE       → 文件系统路径（public / private / tasks root）
  DATA_SERVICE    → 数据查询微服务（HTTP API）
  LLM_QUICK       → 快速问答模型（意图分类、路由）
  LLM_CODING      → 代码生成模型（脚本编写、sbx_run_code）
  LLM_REASONING   → 深度推理模型（规划、摘要）
  LLM_MULTIMODAL  → 多模态模型（图像/表格理解）
  EMBEDDING       → 向量模型（记忆/知识检索）
  AGENT_LOCALE    → 语言方言（zh_CN / en_US）
```

---

## 2. 架构分层规则

### 2.1 模块依赖方向（只能向下依赖）

```
gateway/          ← 入口层（接收外部请求，任务分发）
    ↓
agent.py          ← 编排层（LangGraph 图定义，工具绑定）
    ↓
orchestration/    ← 业务逻辑层（意图解析、DAG 调度、Insight 生成）
    ↓
tools/            ← 原子工具层（LLM 可调用的 @tool 函数）
    ↓
session/          ← 基础设施层（DB 会话、checkpointer）
config/           ← 配置层（env var 统一入口）
workspace/        ← 文件系统层（路径构建、技能加载）
```

**禁止反向依赖**：`tools/` 不得 import `gateway/`，`session/` 不得 import `tools/`，以此类推。

### 2.2 "唯一读取点"约束（不得破坏）

以下约束是 datacloud-analysis 的核心设计决策：

| 职责 | 唯一所有者 | 其他模块的做法 |
|------|-----------|--------------|
| 读取 `DATACLOUD_WORKSPACE_*` env var | `workspace/paths.py` | 接收 `TaskPaths` dataclass，不读 env |
| 读取所有其他 env var | `config/env.py` | import Settings 或其子类 |
| 构建 LangGraph run config | `session/metadata.py` | 调用 `build_run_config()`，不自己构造 dict |
| OpenGauss checkpointer 工厂 | `session/pg_opengauss.py` | import `get_checkpointer`，不自己建连接 |
| Agent 图工厂 | `agent.py::create_agent()` | 调用 `create_agent()`，不自己编译 LangGraph 图 |

### 2.3 重型库只能局部导入

`psycopg`、`langgraph.checkpoint.postgres` 等重型库不得在模块顶层 import，除非该模块的核心职责就是操作它们（如 `session/pg_opengauss.py`）。其他模块在函数体内按需导入：

```python
async def get_checkpointer():
    from psycopg import Connection  # noqa: PLC0415  — 避免进程启动时建立 DB 连接
    conn = Connection.connect(uri, ...)
    ...
```
