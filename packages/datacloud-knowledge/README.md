# datacloud-knowledge

`datacloud-knowledge` 主要提供两类能力：

1. `src/datacloud_knowledge/provider.py` 中的 `FunctionKnowledgeProvider`
2. `src/datacloud_knowledge/cli.py` 中的术语构建相关命令

## FunctionKnowledgeProvider

`FunctionKnowledgeProvider` 是默认的知识提供器，基于包内函数直接完成查询与澄清处理。

### `resolve_field_aliases()`

按作用域解析字段别名，也可以同时解析字段值别名。

```python
from datacloud_knowledge.provider import FunctionKnowledgeProvider

provider = FunctionKnowledgeProvider()
result = provider.resolve_field_aliases(
    terms=["客户", "地区"],
    scope_code="sales",
    library_id="lib_001",
    user_id="user_001",
)
```

### `prepare_query_clarification()`

对待澄清的查询做分析，返回是否需要澄清，以及对应的表单和知识信息。

```python
analysis = provider.prepare_query_clarification(
    query="查询近三个月高价值客户",
    ontology_code="sales",
    structured_input={"query": "查询近三个月高价值客户"},
    mode="query",
)
```

### `finalize_query_clarification()`

把澄清结果回填到结构化输入中，必要时持久化已确认的同义词。

```python
finalized = provider.finalize_query_clarification(
    query="查询近三个月高价值客户",
    ontology_code="sales",
    structured_input={"query": "查询近三个月高价值客户"},
    mode="query",
    needs_clarification=True,
    form="...",
    metadata="...",
    user_id="user_001",
)
```

### `search_terms_by_type()`

按术语类型检索术语，可附带关键词、标签和术语编码过滤。

```python
terms = provider.search_terms_by_type(
    term_type_code="customer",
    keyword="活跃",
    limit=20,
)
```

### 其他常用入口

- `get_provider()`：获取当前全局 provider
- `reset_provider()`：重置全局 provider，测试时常用

默认 provider 为 `FunctionKnowledgeProvider`。也可通过环境变量 `DATACLOUD_KNOWLEDGE_PROVIDER_MODE=function` 显式指定。

## 术语构建 CLI

命令入口来自 `datacloud_knowledge.cli:main`，安装后对应可执行命令为 `datacloud-knowledge`。

### `ensure-schema`

创建或更新术语构建所需的数据库表。

```bash
datacloud-knowledge ensure-schema --schema whale_datacloud
```

常用参数：

- `--reset`：重建表结构
- `--no-seed`：不插入内置术语类型与系统种子数据
- `--create-vector-extension`：尝试创建 `vector` 扩展

### `import-terms`

导入术语构建包。

```bash
datacloud-knowledge import-terms ./path/to/package --schema whale_datacloud
```

### `bootstrap`

一次完成建表、导入和后续回填。

```bash
datacloud-knowledge bootstrap ./path/to/package --schema whale_datacloud
```

### 相关回填

- `backfill-tsvector`：回填术语检索所需的 `tsvector`
- `backfill-embeddings`：回填术语向量

## 最小示例

```python
from datacloud_knowledge.provider import FunctionKnowledgeProvider

provider = FunctionKnowledgeProvider()
result = provider.search_terms_by_type(term_type_code="customer", keyword="重点")
```
