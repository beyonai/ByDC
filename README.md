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

示例使用 `examples/chatbi_demo` 目录，包含 CRM 演示数据和本体资源文件。

#### 1. 配置环境变量

复制模板并填入实际值：

```bash
cd examples/chatbi_demo
cp .demo_env_example .demo_env
```

`.demo_env` 关键配置项：

```ini
# 术语数据库（OpenGauss / PostgreSQL）
DATACLOUD_DB_TYPE=opengauss        # opengauss 或 postgresql
DATACLOUD_DB_HOST=XX.XX.XX.XX
DATACLOUD_DB_PORT=5432
DATACLOUD_DB_DATABASE=postgres
DATACLOUD_DB_SCHEMA=demo_test      # 数据库 schema，同时用于 OWL 数据源文件
DATACLOUD_DB_USER=XX
DATACLOUD_DB_PASSWORD=XX

# LLM 配置
DEMO_API_KEY=sk-xxx
DEMO_MODEL=kimi-k2.6
DEMO_BASE_URL=https://api.moonshot.cn/v1
DEMO_TEMPERATURE=0.6

# 本体资源路径（相对于 chatbi_demo 目录）
DEMO_RESOURCE_PATH=./resource

# SQL 执行器地址（本地直连时留空，走 API 代理时填写）
# DEMO_SQL_EXECUTE_URL=http://host:port/executeSql
```

#### 2. 执行初始化脚本

```bash
cd examples/chatbi_demo
bash init.sh
```

脚本会自动完成：

1. 读取 `resource/object/*/` 下的 `*_dbsource.owl.template`，将占位符替换为 `.demo_env` 中的实际值，渲染结果写入同名 `.owl` 文件（模板文件保持不变，可重复执行）
2. 在数据库中创建 schema（`DATACLOUD_DB_SCHEMA`）
3. 执行 `data/sql/01-crm_demo.sql` — 建表并导入 CRM 演示数据（商机、客户、项目等）
4. 执行 `data/sql/02-term.sql` — 导入本体术语数据（字段映射、别名、知识图谱）

> **注意：** 脚本会自动跳过依赖 pgvector 扩展的向量索引和依赖外部函数的触发器，不影响核心功能。

#### 3. 运行示例

```bash
bash start.sh                     # 正常查询流程（自动加载 .demo_env）
```

> `start.sh` 会自动 `source .demo_env` 后启动脚本，无需手动导出环境变量。



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

