# datacloud-knowledge

<p align="center"> 
  <a href="https://github.com/beyonai/by-datacloud"><img src="https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.12+"></a>
  <a href="https://github.com/beyonai/by-datacloud/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://github.com/beyonai/by-datacloud"><img src="https://img.shields.io/badge/Built%20by-Whale%20DataCloud-blue?style=for-the-badge" alt="Built by Whale DataCloud"></a>
</p>

**DataCloud 2.0 的知识层。** 把业务里说的人话翻成系统能直接用的标准术语、字段别名、澄清结果和知识包 —— 解决"用户怎么说"和"系统怎么懂"之间那道沟。

<table>
<tr><td><b>本体驱动</b></td><td>知识来自术语包、OWL 本体和种子数据，业务规则不硬写进代码。</td></tr>
<tr><td><b>先澄清，再落地</b></td><td>不仅告诉你"查什么"，还告诉你"要不要补问、怎么补问、怎么回填"。</td></tr>
<tr><td><b>薄封装</b></td><td>对外只保留 <code>FunctionKnowledgeProvider</code> 和同名函数 facade，内部直接复用现有实现。</td></tr>
<tr><td><b>运维友好</b></td><td>建表、导入、回填、校验拆成独立 CLI 命令，想单独跑哪一步都可以。</td></tr>
<tr><td><b>适合智能体</b></td><td>输出结构化，方便上层 agent 继续推理和决策。</td></tr>
</table>

---

## 核心能力

| 能力 | 说明 |
|------|------|
| **字段别名解析** | 按作用域解析字段别名，支持字段值别名 |
| **术语检索** | 按术语类型、编码、关键词、标签检索术语 |
| **查询澄清** | 分析查询是否需要澄清，返回澄清表单与知识信息 |
| **澄清回填** | 将澄清结果回填到结构化输入，持久化确认过的同义词 |
| **术语构建 CLI** | 建表、导入、回填、校验和 bootstrap 一站式命令 |

---

## 快速开始

### 安装

```bash
uv sync
```

### Provider API

最常见的入口是 `FunctionKnowledgeProvider`：

```python
from datacloud_knowledge.provider import FunctionKnowledgeProvider

provider = FunctionKnowledgeProvider()

# 字段别名解析
field_result = provider.resolve_field_aliases(
    terms=["客户", "地区"],
    scope_code="sales",
)

# 术语检索
term_result = provider.search_terms_by_type(
    term_type_code="customer",
    keyword="活跃",
    limit=20,
)

# 查询澄清
analysis = provider.prepare_query_clarification(
    query="查询近三个月高价值客户",
    ontology_code="sales",
    structured_input={"query": "查询近三个月高价值客户"},
    mode="query",
)

# 澄清回填
finalized = provider.finalize_query_clarification(
    query="查询近三个月高价值客户",
    ontology_code="sales",
    structured_input={"query": "查询近三个月高价值客户"},
    mode="query",
    needs_clarification=analysis.needs_clarification,
    form=analysis.form,
    metadata=analysis.metadata,
)
```

也可以直接用函数式 facade：

```python
from datacloud_knowledge.provider import search_terms_by_type

result = search_terms_by_type(term_type_code="customer", keyword="重点")
```

### CLI

`datacloud-knowledge` 命令负责环境搭建。典型流程：建表 → 导入 → 回填 → 校验。

```bash
datacloud-knowledge ensure-schema --schema whale_datacloud
datacloud-knowledge import-terms ./path/to/package --schema whale_datacloud
datacloud-knowledge backfill-tsvector --schema whale_datacloud
datacloud-knowledge backfill-embeddings --schema whale_datacloud
datacloud-knowledge verify-schema --schema whale_datacloud
```

或者一步到位：

```bash
datacloud-knowledge bootstrap ./path/to/package --schema whale_datacloud
```

| 命令 | 说明 |
|------|------|
| `ensure-schema` | 创建或更新知识库所需表结构 |
| `verify-schema` | 检查核心表是否存在 |
| `import-terms` | 导入 OWL / 术语知识包 |
| `backfill-tsvector` | 回填术语检索所需的 tsvector |
| `backfill-embeddings` | 回填术语向量 |
| `bootstrap` | 建表 + 导入 + 回填一次完成 |

> **注意：** `--reset` 会重建表结构，属于破坏性操作，仅在明确需要重新初始化时使用。

---

## 适用场景

- 把自然语言稳定映射到标准字段
- 查询前判断是否需要补问
- 知识包导入数据库后继续检索、回填、校验
- 给上层分析智能体提供稳定的知识入口

如果你在做 DataCloud 的分析链路、查询规划链路或知识增强链路，这个包就是底座。

---

## 项目结构

```
src/datacloud_knowledge/
  provider.py      # 知识 Provider facade
  cli.py           # 术语构建 CLI
  __init__.py      # 包级导出
db/
  ddl/knowledge/   # DDL 脚本
  seed/knowledge/  # 种子数据
  migrations/      # 数据库迁移
```

---

## 开发

```bash
uv sync                                    # 安装依赖
uv run ruff format .                       # 格式化
uv run ruff check . --fix                  # Lint
uv run mypy src/datacloud_knowledge        # 类型检查
uv run pytest                              # 单元测试
uv run pytest -m db_integration            # 数据库集成测试
```

---

## License

[MIT](https://github.com/beyonai/by-datacloud/blob/main/LICENSE)
