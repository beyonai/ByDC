# dataCloud 2.0

dataCloud 是一个数智引擎，通过智能构建企业级知识网络，面向大模型、智能应用和业务人员输出业务化组件能力，提升企业数据获取效率与推理准确性。

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

## 开发指南

### 环境要求

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/) >= 0.7

### 快速开始

```bash
# 1) 安装所有 workspace 依赖
uv sync

# 2) 运行 analysis 包（示例）
uv run --package datacloud-analysis python -m datacloud_analysis

# 3) 质量检查
uv run ruff format .
uv run ruff check .
uv run mypy .
uv run pytest
```

### Monorepo 结构

```text
whale_datacloud/
├── pyproject.toml
├── uv.lock
├── README.md
├── docs/
├── src/
├── tests/
├── packages/
│   ├── datacloud-analysis/
│   ├── datacloud-data/
│   ├── datacloud-knowledge/
│   └── datacloud-memory/
└── examples/
    └── sales_analysis_demo/
        ├── frontend/
        ├── backend/
        │   └── datacloud_data_service/
        └── mock_env/
```

### Workspace 依赖管理

根 `pyproject.toml` 中通过 `tool.uv.workspace` 管理成员，当前为：

- `packages/datacloud-analysis`
- `packages/datacloud-data`
- `packages/datacloud-knowledge`
- `packages/datacloud-memory`

示例：为 `datacloud-analysis` 添加依赖：

```bash
uv add --package datacloud-analysis <package>
```