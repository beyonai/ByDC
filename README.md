# dataCloud 2.0

dataCloud是一个数智引擎，通过智能构建企业级知识网络，面向大模型、智能应用、业务人员的输出业务化组件能力，提升企业数据获取效率及应用推理的准确性。

## 项目结构与核心模块

dataCloud 2.0 采用 Monorepo 结构，包含以下核心服务及应用模块：

1. **datacloud-agent** - 超级分析智能体框架
   - 核心智能体框架，底层依赖 `datacloud-data-service` 与 `datacloud-memory`。
   - 基于LangGraph框架的极简主义Agent设计
   - 5个原子工具：know/query/compute/render/store
   - 支持会话树、分支探索、自举能力

2. **datacloud-apps** - 应用层结构
   - 利用 `datacloud-agent` 开发的具体应用集合。
   - 目录结构：下级为具体应用名称，每个单应用内固定包含前端(frontend)和后端(backend)目录。

3. **datacloud-data-service** - 数据查询服务
   - NL2Data数据查询执行
   - 行列权限控制
   - 异构数据库适配

4. **datacloud-knowledge-service** - 知识查询服务
   - 根据问题检索知识（业务知识、本体知识）
   - 生成并返回数据查询计划
   - 术语自动发现与沉淀

5. **datacloud-memory** - 记忆服务
   - 短期记忆（会话级）
   - 长期记忆（跨会话）
   - 记忆检索与压缩

6. **datacloud-mock** - 数据仿真服务
   - 提供各类场景下所需的数据仿真、模拟能力。

## 命名规范

各模块与目录遵循以下核心标准与最佳实践：
- 统一使用**小写字母**。
- 统一使用**连字符（`-`）**分隔单词，禁止使用下划线（`_`）（例如 `datacloud-agent`，不使用 `datacloud_agent`）。
- 命名清晰描述职责，始终保持风格一致性。


## 开发指南

### 环境要求

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/) >= 0.7

### 快速开始

```bash
# 1. 安装所有依赖（根项目 + 所有子项目）
uv sync

# 2. 运行特定子项目
uv run --package datacloud-agent python -m datacloud_agent

# 3. 代码检查
uv run ruff format .      # 格式化
uv run ruff check .       # Lint 检查
uv run mypy .             # 类型检查
uv run pytest             # 运行测试
```

### Workspace 结构

本项目使用 uv workspace 管理多子项目（Monorepo）：

```text
whale-datacloud/
├── pyproject.toml                # 根项目配置 + workspace 定义
├── uv.lock                       # 统一依赖锁定文件
├── src/whale_datacloud/          # 根包（跨应用可共享的核心基础代码）
├── tests/                        # 根项目测试（整体验证POC或集成端到端测试）
├── datacloud-agent/              # 超级分析智能体框架
├── datacloud-apps/               # 具体 Agent 应用落地的目录（内含各应用的前后端）
├── datacloud-data-service/       # 数据查询服务
├── datacloud-knowledge-service/  # 知识查询服务
├── datacloud-memory/             # 记忆服务
└── datacloud-mock/               # 数据仿真服务
```

### 添加依赖

```bash
# 为根项目添加依赖
uv add <package>

# 为特定子项目添加依赖
uv add --package datacloud-agent <package>
```

### 子项目间依赖

在 uv workspace 中，子项目可以相互依赖：

```toml
# datacloud-agent/pyproject.toml
dependencies = [
    "langgraph>=0.2.0",
    # 添加其他 workspace 成员作为依赖
    "datacloud-knowledge-service",
    "datacloud-data-service",
    "datacloud-memory",
]

[tool.uv.sources]
# 声明 workspace 依赖来源
datacloud-knowledge-service = { workspace = true }
datacloud-data-service = { workspace = true }
datacloud-memory = { workspace = true }
```

然后在代码中直接导入：

```python
from datacloud_knowledge_service import some_function
from datacloud_data_service import DataClient
from datacloud_memory import MemoryStore
```

### 依赖管理要点

1. **根项目配置**：在根 `pyproject.toml` 中声明所有 workspace 成员
   ```toml
   [tool.uv.workspace]
   members = [
       "datacloud-agent",
       "datacloud-data-service",
       "datacloud-knowledge-service",
       "datacloud-memory",
       "datacloud-mock",
       "datacloud-apps/*",
   ]

   [tool.uv.sources]
   datacloud-agent = { workspace = true }
   datacloud-data-service = { workspace = true }
   datacloud-knowledge-service = { workspace = true }
   datacloud-memory = { workspace = true }
   datacloud-mock = { workspace = true }
   ```

2. **统一锁定文件**：所有子项目共享同一个 `uv.lock`