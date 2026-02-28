# dataCloud 2.0

dataCloud是一个数智引擎，通过智能构建企业级知识网络，面向大模型、智能应用、业务人员的输出业务化组件能力，提升企业数据获取效率及应用推理的准确性。

## 核心服务

dataCloud 2.0 包含4个核心服务模块：

1. **datacloud-agent** - 超级分析智能体
   - 基于LangGraph框架的极简主义Agent设计
   - 5个原子工具：know/query/compute/render/store
   - 支持会话树、分支探索、自举能力

2. **datacloud-knowledge-service** - 知识服务
   - 根据问题检索知识（业务知识、本体知识）
   - 生成并返回数据查询计划
   - 术语自动发现与沉淀

3. **datacloud-data-service** - 数据服务
   - NL2Data数据查询执行
   - 行列权限控制
   - 异构数据库适配

4. **datacloud-memory** - 记忆服务
   - 短期记忆（会话级）
   - 长期记忆（跨会话）
   - 记忆检索与压缩

## 仓库命名规范

所有仓库遵循GitHub命名最佳实践：
- 使用小写字母
- 使用连字符（`-`）分隔单词
- 命名清晰、描述性
- 保持一致性

详细命名规范请参考：[REPOSITORY_NAMING.md](./REPOSITORY_NAMING.md)


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

本项目使用 uv workspace 管理多子项目：

```
whale-datacloud/
├── pyproject.toml          # 根项目配置 + workspace 定义
├── uv.lock                 # 统一依赖锁定文件
├── src/whale_datacloud/    # 根包（共享代码）
├── tests/                  # 根项目测试
├── datacloud-agent/        # Agent 服务子项目
├── datacloud-data-service/ # 数据服务子项目
├── datacloud-knowledge-service/  # 知识服务子项目
└── datacloud-memory/       # 内存服务子项目
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
   ]

   [tool.uv.sources]
   datacloud-agent = { workspace = true }
   datacloud-data-service = { workspace = true }
   datacloud-knowledge-service = { workspace = true }
   datacloud-memory = { workspace = true }
   ```

2. **统一锁定文件**：所有子项目共享同一个 `uv.lock`