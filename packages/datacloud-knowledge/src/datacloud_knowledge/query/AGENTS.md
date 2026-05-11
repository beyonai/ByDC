# AGENTS.md

**Module:** query
**Purpose:** NL-to-semantic-tree query engine plus recall/search utilities

## OVERVIEW

Core query domain for turning natural language into semantic tree / SQL-like knowledge graph operations. `sql_engine.py` is the main engine; subpackages provide BM25/vector/substr recall, fuzzy matching, and embeddings.

## STRUCTURE

```text
query/
├── sql_engine.py              # SQLKnowledgeGraphQuery, TreeNode, singleton helpers
├── vocab_cache.py             # VocabularyCache and cache env constants
├── search/                    # BM25, vector, substring, jieba, RRF
├── fuzzy/                     # RapidFuzz matcher and public types
└── embedding/                 # EmbeddingService facade
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Main query service | `sql_engine.py:SQLKnowledgeGraphQuery` | Public via `query/__init__.py` and top-level lazy exports |
| Singleton lifecycle | `sql_engine.py:get_singleton_service()` | Tests should call reset helper when needed |
| Semantic tree conversion | `sql_engine.py:nl_to_semantic_tree()` | Public export |
| BM25 recall | `search/bm25.py` | Checks column capability and falls back |
| Vector recall | `search/vector.py`, `search/vector_validation.py` | pgvector readiness and search |
| Substring/jieba recall | `search/substring_recall.py`, `search/jieba_recall.py` | Chinese term recall helpers |
| RRF fusion | `search/rrf.py` | Combines recall candidates |
| Fuzzy matching | `fuzzy/rapidfuzz_matcher.py` | Public factory in `fuzzy/__init__.py` |

## PUBLIC SURFACE

- `query/__init__.py` exports `SQLKnowledgeGraphQuery`, `TreeNode`, `create_sql_graph_query`, `get_singleton_service`, `nl_to_semantic_tree`, `reset_singleton_service`.
- `query/search/__init__.py` exports BM25/vector/jieba/substring/RRF functions and result dataclasses.
- `query/fuzzy/__init__.py` exports config/result types plus matcher factory helpers.

## CONVENTIONS

- Keep top-level query imports compatible with lazy top-level package exports.
- Search SQL should use bare table names; schema-specific introspection must call `resolve_knowledge_schema()`.
- BM25 uses PostgreSQL `tsvector`/`ts_rank_cd`; do not concatenate raw user tsquery text.
- Vector code assumes 1024-dim embeddings where DB schema/indexes expect that shape.
- Cache/singleton tests should reset module state rather than depending on test order.

## TESTS

| Area | Tests |
|------|-------|
| Vector readiness | `tests/query/search/test_vector_validation.py` |
| BM25 SQL compatibility | `tests/intent/test_bm25_search_compat.py` |
| Scope SQL compatibility | `tests/intent/test_scope_user_sql_compat.py` |

## ANTI-PATTERNS

- Do not expand `sql_engine.py` with unrelated provider/intent responsibilities; use `provider.py` or `intent/`.
- Do not add production `print()` despite the doctest-style example near the bottom of `sql_engine.py`.
- Do not add schema-qualified `whale_datacloud.*` SQL in search paths.

## NOTES

- `sql_engine.py` is the largest source file and has pre-existing LSP/Pyright diagnostics.
- `vocab_cache.py` has a root ruff file ignore for pickle use; do not copy that pattern elsewhere.
