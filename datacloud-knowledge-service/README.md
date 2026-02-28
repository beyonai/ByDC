# datacloud-knowledge-service

知识服务（Knowledge Service）是 dataCloud 2.0 的核心服务之一，负责根据用户问题检索业务知识和本体知识，生成并返回数据查询计划。

## 核心定位

**业务翻译**：将自然语言问题转化为结构化的逻辑步骤和数据查询计划。

## 核心功能

### 1. 知识检索

- **业务知识检索**：从企业知识库中检索相关业务规则、术语定义等
- **本体知识检索**：从本体系统中检索实体、属性、关系等结构化知识
- **语义匹配**：基于向量检索和语义理解进行知识匹配

### 2. 查询计划生成

- **意图理解**：理解用户问题的真实意图
- **查询分解**：将复杂问题分解为多个查询步骤
- **计划优化**：优化查询计划，提高执行效率

### 3. 术语管理

- **术语自动发现**：从用户提问中自动发现新术语
- **术语沉淀**：将术语保存到术语库中
- **术语关联**：建立术语之间的关系

### 4. 知识增强

- **渐进式加载**：按需加载知识，避免上下文窗口溢出
- **知识冲突检测**：检测和解决知识冲突
- **知识版本管理**：支持知识的版本管理和更新

## 技术架构

### 核心技术

- **向量检索**：基于嵌入向量的语义检索
- **本体查询**：基于图数据库的本体查询
- **查询规划**：基于LLM的查询计划生成

### 技术栈

```python
# 向量检索
- LangChain: 向量存储和检索
- Chroma/Weaviate: 向量数据库

# 本体查询
- 图数据库: 本体关系查询
- SPARQL: 本体查询语言

# LLM集成
- LangChain: LLM调用和提示工程
- OpenAI/Claude: 大语言模型
```

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，配置向量数据库、本体服务等

# 启动服务
python -m datacloud_knowledge_service.main
```

## API 接口

### 生成查询计划

```http
POST /api/v1/query-plan
Content-Type: application/json

{
  "question": "王小明作为销售是否优秀？",
  "context": {
    "session_id": "session-001",
    "user_id": "user-001"
  }
}
```

### 检索知识

```http
POST /api/v1/knowledge/retrieve
Content-Type: application/json

{
  "query": "销售KPI评估标准",
  "knowledge_types": ["business", "ontology"]
}
```

## 项目结构

```
datacloud-knowledge-service/
├── README.md              # 本文件
├── requirements.txt       # Python依赖
├── .env.example          # 环境变量示例
├── src/
│   ├── knowledge/        # 知识检索逻辑
│   ├── planner/          # 查询计划生成
│   ├── terminology/      # 术语管理
│   └── api/              # API接口
├── tests/                # 测试文件
└── docs/                 # 文档
```

## 相关文档

- [知识服务模块设计](../../story/V202602/feature_datacloud2.0设计/知识服务_模块设计/知识服务_模块设计.md)
- [dataCloud 2.0 概要设计](../../story/V202602/feature_datacloud2.0设计/dataCloud2.0概要设计.md)

## 许可证

MIT License

