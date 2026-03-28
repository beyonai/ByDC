# AGENTS.md

**Module:** query
**Purpose:** 自然语言图谱查询 — NL→语义树→SQL

---

## Overview

核心查询模块：将自然语言问题转化为结构化语义树，支持 N 跳子图查询、模糊匹配、术语提取。

## Structure

```
query/
├── sql_engine.py      # 主查询引擎（SQLKnowledgeGraphQuery）
├── vocab_cache.py     # 术语缓存
└── fuzzy/             # 模糊匹配
    ├── matcher.py     # 抽象接口
    ├── rapidfuzz_matcher.py  # 实现
    └── types.py       # 类型定义
```

## Where to Look

| Task | Location |
|------|----------|
| NL→语义树 | `sql_engine.py:nl_to_semantic_tree()` |
| 提取实体 | `sql_engine.py:SQLKnowledgeGraphQuery.extract_entities()` |
| N跳查询 | `sql_engine.py:query_n_hop_subgraph()` |
| 模糊匹配 | `fuzzy/rapidfuzz_matcher.py:RapidFuzzMatcher` |
| 缓存管理 | `vocab_cache.py:VocabularyCache` |

## Key Algorithms

### 实体提取（双向最大匹配）
- `_forward_max_match()` — 正向
- `_backward_max_match()` — 逆向
- `_bidirectional_max_match()` — 合并策略

### 术语匹配
- 精确匹配 → 名称索引
- 模糊匹配 → RapidFuzz（阈值可配置）
- 别名/拼音匹配 → 预处理索引

## Conventions

- **单例模式**：`get_singleton_service()` 返回全局实例
- **缓存键**：SHA256(question + hops)
- **异步友好**：连接池预热 `prewarm()`

## Notes

- `sql_engine.py` 1436 行 — 最大的文件，核心逻辑
- 测试时用 `reset_singleton_service()` 重置状态