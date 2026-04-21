# AGENTS.md

**Module:** query
**Purpose:** 自然语言图谱查询 — NL→语义树→SQL

---

## Overview

核心查询模块：将自然语言问题转化为结构化语义树，支持 N 跳子图查询、多路召回、模糊匹配、术语提取。

## Structure

```
query/
├── sql_engine.py          # 主查询引擎 SQLKnowledgeGraphQuery（1677L）
├── vocab_cache.py         # 术语缓存 VocabularyCache
├── search/                # 多路召回
│   ├── bm25.py            # BM25 全文搜索（单字 + jieba 分词）
│   ├── vector.py          # pgvector 向量相似度搜索
│   ├── vector_validation.py # 向量就绪校验
│   ├── substring_recall.py # 双向子串匹配
│   ├── jieba_recall.py    # jieba 分词召回
│   └── rrf.py             # Reciprocal Rank Fusion 融合
├── fuzzy/                 # 模糊匹配
│   ├── matcher.py         # 抽象接口
│   ├── rapidfuzz_matcher.py # RapidFuzz 实现
│   └── types.py           # FuzzyConfig/FuzzyMatch
└── embedding/             # 向量嵌入
    └── service.py         # EmbeddingService
```

## Where to Look

| Task | Location |
|------|----------|
| NL→语义树 | `sql_engine.py:SQLKnowledgeGraphQuery.query()` |
| 实体提取 | `sql_engine.py:extract_entities()` |
| N跳子图查询 | `sql_engine.py:query_n_hop_subgraph()` |
| BM25 搜索 | `search/bm25.py:bm25_search()` |
| 向量搜索 | `search/vector.py:vector_search()` |
| 子串召回 | `search/substring_recall.py:substring_recall()` |
| 模糊匹配 | `fuzzy/rapidfuzz_matcher.py:RapidFuzzMatcher` |
| 缓存管理 | `vocab_cache.py:VocabularyCache` |

## Key Algorithms

- **双向最大匹配**: `_forward_max_match()` + `_backward_max_match()` → `_bidirectional_max_match()`
- **BM25**: PostgreSQL `tsvector` + `ts_rank_cd`，支持单字分词和 jieba 词级分词
- **向量搜索**: pgvector HNSW 索引，1024 维 embedding，余弦距离
- **分区召回**: `*_partitioned()` 变体按 `term_type_code` 分区取 top-N

## Conventions

- **单例模式**: `get_singleton_service()` / `reset_singleton_service()`
- **SQL 裸表名**: search/ 中所有 SQL 不硬编码 schema，依赖 engine `connect_args` 设置 `search_path`
- **information_schema 查询**: `bm25.py` 用 `resolve_knowledge_schema()` 动态获取 schema 名

## Notes

- `sql_engine.py` 1677 行 — 最大的文件，核心逻辑
- `search/` 7 个文件 — BM25/向量/子串三路召回 + RRF 融合