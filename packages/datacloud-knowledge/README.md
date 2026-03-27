# datacloud-knowledge

知识服务 SDK — 术语检索、本体查询、N跳子图查询。
将自然语言转化为结构化查询计划。

## 安装

```bash
uv add datacloud-knowledge
```

## 功能

- **术语检索**: 基于正向/逆向最大匹配的术语提取
- **本体查询**: OWL 关系解析与知识图谱构建
- **N跳子图查询**: 自然语言→语义树→SQL 查询
- **模糊匹配**: 基于 RapidFuzz 的相似度匹配

## 快速开始

```python
from datacloud_knowledge.query import SQLKnowledgeGraphQuery

# 获取单例服务
query_service = SQLKnowledgeGraphQuery.get_instance()

# 执行查询
result = query_service.query("查询所有客户")
```

## 开发

```bash
# 安装依赖
uv sync

# 格式化 + Lint
uv run ruff format .
uv run ruff check .

# 类型检查
uv run mypy .

# 运行测试
uv run pytest
```