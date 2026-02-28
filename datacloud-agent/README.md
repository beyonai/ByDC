# datacloud-agent

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

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，配置LLM API密钥等

# 启动服务
python -m datacloud_agent.main
```

## 项目结构

```
datacloud-agent/
├── README.md              # 本文件
├── requirements.txt       # Python依赖
├── .env.example          # 环境变量示例
├── src/
│   ├── agent/            # Agent核心逻辑
│   ├── tools/            # 5个原子工具实现
│   ├── memory/           # 记忆管理
│   ├── events/           # 事件系统
│   └── workspace/        # 工作空间管理
├── tests/                # 测试文件
└── docs/                 # 文档
```

## 相关文档

- [详细设计文档](../../story/V202602/feature_datacloud2.0设计/超级数据分析智能体_模块设计/超级分析智能体_模块设计.md)
- [dataCloud 2.0 概要设计](../../story/V202602/feature_datacloud2.0设计/dataCloud2.0概要设计.md)

## 许可证

MIT License

