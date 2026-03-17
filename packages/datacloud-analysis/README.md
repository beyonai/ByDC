# datacloud-analysis

超级分析智能体（Super Analysis Agent）是 dataCloud 2.0 的核心智能体服务，基于 LangGraph 框架实现极简主义设计，提供智能数据分析能力。

## 核心定位

**中枢大脑**：调度资源与工具，实现从自然语言问题到数据洞察的完整闭环。

## 核心功能

### 1. 极简工具集（5个原子工具）

| 工具名称 | 功能描述 | 对应模块 |
|---------|---------|---------|
| `know` | 知识检索与规划工具 | 知识服务 |
| `query` | 数据查询工具 | 数据服务 |
| `compute` | 计算执行工具 | 沙箱与文件系统 |
| `render` | 渲染生成工具 | 分析界面 |
| `store` | 存储管理工具 | 资产沉淀 |

### 2. 会话管理

- **会话树结构**：支持分支探索和回溯
- **多会话隔离**：动态上下文压缩、多线程会话隔离
- **长效决策记忆**：确保决策过程的逻辑连续性

### 3. 事件驱动机制

- **完全可观察**：细粒度事件输出（turn_start, tool_call_start, tool_call_complete等）
- **实时反馈**：通过SSE协议实时推送执行状态
- **中断恢复**：支持消息队列和任务中断恢复

### 4. 自举能力

- **动态工具注册**：Agent可以自己生成新工具
- **Skill扩展**：按需加载Skills，自动注册为临时工具
- **资产沉淀**：生成的工具自动保存到Skills目录

### 5. 自我进化机制

- **执行反馈学习**：记录每次工具调用的执行结果
- **决策模式沉淀**：将成功的决策过程抽象为可复用模式
- **跨会话经验复用**：经验沉淀到全局经验库

## 技术架构

### 框架选型

- **核心框架**：LangGraph（状态图驱动）
- **工具集成**：LangChain
- **状态管理**：LangGraph State
- **事件系统**：基于LangGraph StreamEvents

### 技术栈

```python
# 核心框架
- LangGraph: Agent状态图和流程编排
- LangChain: 工具集成和LLM调用
- Pydantic: 状态和工具的数据模型

# 事件系统
- 自定义EventBus: 基于LangGraph的StreamEvents
- SSE (Server-Sent Events): 实时事件推送

# 状态管理
- LangGraph State: 会话状态和分支管理
- Redis: 跨会话经验库（可选）

# 工作空间
- 文件系统: 基于LangGraph状态的工作空间管理
```

## 开发工具

### Superpowers 插件

本项目已集成 **Superpowers** 插件，提供完整的软件开发工作流支持：

- **测试驱动开发（TDD）**：强制执行 RED-GREEN-REFACTOR 循环
- **系统化调试**：结构化的问题诊断和根因追踪
- **子代理驱动开发**：多阶段审查和代码质量保证
- **计划编写与执行**：将设计分解为可执行的任务
- **代码审查**：自动化的代码审查流程

**插件位置**：`.cursor/plugins/superpowers`

**使用方式**：在 Cursor Agent chat 中，插件会自动触发相关技能。例如：
- "help me plan this feature" - 触发计划编写技能
- "let's debug this issue" - 触发系统化调试技能

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，配置LLM API密钥等

# 启动服务
python -m datacloud_analysis.main
```

## 项目结构 (src-layout)

本项目采用 Python 官方推荐的 `src-layout` 目录结构，以实现代码和配置的分离、避免潜在导入错误，并保持根目录清晰。

```text
datacloud-analysis/
├── pyproject.toml         # 现代 Python 项目配置（替代 setup.py，配置依赖和打包工具）
├── requirements.txt       # 具体环境依赖包清单（用于快速安装依赖）
├── .env.example           # 环境变量配置示例（本地复制为 .env 使用）
├── README.md              # 项目总体说明文档
├── docs/                  # 详细的使用手册、API 文档、设计文档及架构图等
├── scripts/               # 运维辅助工具脚本（如：部署脚本、测试工具、大模型调试脚本等）
├── tests/                 # 测试代码目录，与源码结构分离
│   ├── conftest.py        # pytest 共享的 fixtures 与测试配置
│   ├── __init__.py        # 使测试目录成为一个包
│   └── ...                # 单元测试与集成测试文件存放处
└── src/                   # 核心项目源码集中存放处（src 目录作为顶层隔离）
    └── datacloud_analysis/   # 核心 Python 包（实际代码写在这里）
        ├── __init__.py    # 包声明文件
        ├── main.py        # 服务入口文件或核心启动点
        ├── agent/         # 存放超级分析 Agent 的核心逻辑：状态图编排、决策、生命周期等
        │   └── __init__.py
        ├── tools/         # 存放原子工具（know, query, compute, render, store）及具体实现
        │   └── __init__.py
        ├── memory/        # 记忆管理模块：上下文压缩、分支状态维护及长效/短效存储策略
        │   └── __init__.py
        ├── events/        # 事件系统：用于事件总线 (EventBus)、SSE 推送机制及流式状态分发
        │   └── __init__.py
        └── workspace/     # 工作空间管理：文件系统操作与资源沙箱隔离逻辑
            └── __init__.py
```

### 为什么使用 src-layout？

1. **防止导入混淆**：本地开发时如果不经意在根目录运行代码，往往会依赖本地路径隐式加载代码。`src/` 增加了一层隔离层，强迫你依赖被“安装”的包导入，防止意外测试失败。
2. **测试与分发更可靠**：能确保使用 `pytest` 等测试工具测到的是你将来发布打包的代码结构，而不是因为恰好文件都在当前路径下而通过的错误代码。建议搭配 `pip install -e .` 或 `poetry` 管理。（基于 PEP 517 / PEP 660）
3. **保持根目录清晰**：让项目根目录下只专注配置类文件（如 `.env`, `.gitignore`, `pyproject.toml` 等）与文档，所有的核心业务逻辑被完美封装隔离在 `src/package_name/` 中。
## 相关文档

- [详细设计文档](../../story/V202602/feature_datacloud2.0设计/超级数据分析智能体_模块设计/超级分析智能体_模块设计.md)
- [dataCloud 2.0 概要设计](../../story/V202602/feature_datacloud2.0设计/dataCloud2.0概要设计.md)

## 许可证

MIT License

