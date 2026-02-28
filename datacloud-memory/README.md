# datacloud-memory

记忆服务（Memory Service）是 dataCloud 2.0 的核心服务之一，负责管理Agent的短期记忆和长期记忆，支持跨会话的经验复用。

## 核心定位

**记忆中枢**：管理Agent的记忆系统，确保决策过程的逻辑连续性和经验积累。

## 核心功能

### 1. 短期记忆管理

- **会话级记忆**：存储当前会话的对话历史、工具调用历史等
- **上下文压缩**：动态压缩上下文，避免超出LLM上下文窗口
- **记忆检索**：基于关键词、语义等检索相关记忆

### 2. 长期记忆管理

- **跨会话记忆**：存储跨会话共享的经验和知识
- **决策模式沉淀**：将成功的决策过程保存为可复用模式
- **查询模板沉淀**：将成功的查询逻辑保存为查询模板
- **术语库管理**：管理企业术语库，支持术语自动发现

### 3. 记忆检索

- **向量检索**：基于语义相似度的记忆检索
- **关键词检索**：基于关键词的记忆检索
- **时间检索**：基于时间范围的记忆检索

### 4. 记忆优化

- **记忆压缩**：压缩和摘要长期记忆
- **记忆去重**：去除重复的记忆内容
- **记忆版本管理**：管理记忆的版本和更新历史

## 技术架构

### 三层记忆架构

```
┌─────────────────────────────────────┐
│  工作记忆（任务级，临时）              │
│  - 当前任务的中间结果                 │
│  - 任务执行状态                       │
└─────────────────────────────────────┘
           ↓
┌─────────────────────────────────────┐
│  短期记忆（会话级，持久化）            │
│  - 对话历史（JSONL格式）              │
│  - 工具调用历史                       │
│  - 会话状态                           │
└─────────────────────────────────────┘
           ↓
┌─────────────────────────────────────┐
│  长期记忆（跨会话，共享）              │
│  - 决策模式库（Markdown格式）         │
│  - 查询模板库（JSON格式）             │
│  - 术语库（数据库）                   │
│  - 经验库（向量数据库）               │
└─────────────────────────────────────┘
```

### 技术栈

```python
# 存储后端
- 文件系统: 短期记忆（JSONL）、长期记忆（Markdown）
- 向量数据库: Chroma/Weaviate（语义检索）
- 关系数据库: PostgreSQL（术语库、元数据）

# 检索技术
- LangChain: 向量检索和语义检索
- 自定义检索: 关键词检索、时间检索

# 压缩技术
- LLM摘要: 使用LLM压缩长文本
- 重要性排序: 基于重要性保留关键记忆
```

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，配置存储后端、向量数据库等

# 启动服务
python -m datacloud_memory.main
```

## API 接口

### 保存短期记忆

```http
POST /api/v1/memory/short-term
Content-Type: application/json

{
  "session_id": "session-001",
  "content": {
    "type": "message",
    "role": "user",
    "text": "王小明作为销售是否优秀？"
  }
}
```

### 检索长期记忆

```http
POST /api/v1/memory/long-term/retrieve
Content-Type: application/json

{
  "query": "销售评估模式",
  "memory_types": ["decision_pattern", "query_template"],
  "limit": 10
}
```

### 保存决策模式

```http
POST /api/v1/memory/decision-pattern
Content-Type: application/json

{
  "pattern_name": "销售员工评估模式",
  "problem_type": "销售评估",
  "tool_sequence": [...],
  "success_rate": 0.95
}
```

## 项目结构

```
datacloud-memory/
├── README.md              # 本文件
├── requirements.txt       # Python依赖
├── .env.example          # 环境变量示例
├── src/
│   ├── short_term/       # 短期记忆管理
│   ├── long_term/        # 长期记忆管理
│   ├── retrieval/        # 记忆检索
│   ├── compression/      # 记忆压缩
│   └── api/              # API接口
├── tests/                # 测试文件
└── docs/                 # 文档
```

## 文件存储结构

```
~/.datacloud/
├── memory/                        # 公共长期记忆
│   ├── memory.md
│   └── memory-datacloud.md
├── {userId}_public/
│   ├── memory/                    # 用户公共长期记忆
│   └── session-{session_id}/
│       └── short-memory.jsonl     # 短期记忆
└── {userId}_private/
    └── .datacloud/workspaces/
        └── session-{session_id}/
            └── state.json         # 会话状态
```

## 相关文档

- [dataCloud 2.0 概要设计](../../story/V202602/feature_datacloud2.0设计/dataCloud2.0概要设计.md)
- [超级分析智能体模块设计](../../story/V202602/feature_datacloud2.0设计/超级数据分析智能体_模块设计/超级分析智能体_模块设计.md)

## 许可证

MIT License

