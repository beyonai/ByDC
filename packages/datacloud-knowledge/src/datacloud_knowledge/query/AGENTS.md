# AGENTS.md

**Module:** query
**Purpose:** Search recall, fuzzy matching, and embedding utilities

## OVERVIEW

Subpackages provide BM25/vector/substr recall, fuzzy matching, and embeddings. Used by `intent/` and `knowledge_search/` modules.

## STRUCTURE

```text
query/
├── search/                    # BM25, vector, substring, jieba, RRF
├── fuzzy/                     # RapidFuzz matcher and public types
└── embedding/                 # EmbeddingService facade
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| BM25 recall | `search/bm25.py` | Checks column capability and falls back |
| Vector recall | `search/vector.py`, `search/vector_validation.py` | pgvector readiness and search |
| Substring/jieba recall | `search/substring_recall.py`, `search/jieba_recall.py` | Chinese term recall helpers |
| RRF fusion | `search/rrf.py` | Combines recall candidates |
| Fuzzy matching | `fuzzy/rapidfuzz_matcher.py` | Public factory in `fuzzy/__init__.py` |

## PUBLIC SURFACE

- `query/search/__init__.py` exports BM25/vector/jieba/substring/RRF functions and result dataclasses.
- `query/fuzzy/__init__.py` exports config/result types plus matcher factory helpers.

## CONVENTIONS

- Search SQL should use bare table names; schema-specific introspection must call `resolve_knowledge_schema()`.
- BM25 uses PostgreSQL `tsvector`/`ts_rank_cd`; do not concatenate raw user tsquery text.
- Vector code assumes 1024-dim embeddings where DB schema/indexes expect that shape.

## TESTS

| Area | Tests |
|------|-------|
| Vector readiness | `tests/query/search/test_vector_validation.py` |
| BM25 SQL compatibility | `tests/intent/test_bm25_search_compat.py` |
| Scope SQL compatibility | `tests/intent/test_scope_user_sql_compat.py` |

## ANTI-PATTERNS

- Do not add schema-qualified `whale_datacloud.*` SQL in search paths.
