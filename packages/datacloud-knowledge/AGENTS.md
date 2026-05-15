# AGENTS.md — datacloud-knowledge

**Package:** datacloud-knowledge (workspace member of by-datacloud)
**Python:** >=3.12
**Toolchain:** uv + ruff + mypy (inherited from root workspace)

## OVERVIEW

`datacloud-knowledge` is the knowledge SDK for term retrieval, ontology import/export, intent disambiguation, and NL-to-knowledge-query support. It bridges the gap between "what users say" and "what the system understands."

**Architecture (post-restructure, 2026-05):** Seven top-level modules with strict layering:

```
provider.py (public API facade)
    ├── adapters/        ← DB access (factory + OpenGauss backend)
    ├── contracts/       ← interfaces & shared types (no deps)
    ├── i18n/            ← LLM prompt i18n
    ├── ingestion/       ← OWL package import & generation
    ├── intent/          ← disambiguation, clarification, score update, types
    └── retrieval/       ← recall, matching, search, embeddings, tokenizers

cli.py → adapters/ + ingestion/
```

### Dependency flow (hard)

```
provider  →  adapters + retrieval + intent
intent    →  retrieval + contracts + adapters
retrieval →  contracts + adapters
contracts →  (zero external deps)
adapters  →  contracts
i18n      →  (pure data, zero deps)
ingestion →  adapters + contracts
```

## STRUCTURE

```
packages/datacloud-knowledge/
├── pyproject.toml                    # Package metadata (version: 0.1.0), console_scripts
├── src/datacloud_knowledge/
│   ├── __init__.py                   # Exports __version__ = "0.2.0"
│   ├── cli.py                        # CLI entry: datacloud-knowledge (6 commands)
│   ├── provider.py                   # Public API facade (6 functions)
│   │
│   ├── adapters/                     # DB access layer (factory + registry)
│   │   ├── __init__.py               #   Factories: create_reader/engine/writer
│   │   │                             #   Schema: ensure_schema, verify_schema
│   │   │                             #   Backfill: backfill_tsvector, backfill_embeddings
│   │   │                             #   Bulk import: create_bulk_importer
│   │   │                             #   Clarification persist: store_clarification_results
│   │   └── opengauss/                #   OpenGauss/PostgreSQL backend (ONLY registered backend)
│   │       ├── reader.py             #     PostgresTermReader (TermReader impl)
│   │       ├── writer.py             #     PostgresTermWriter (TermWriter impl)
│   │       ├── engine.py             #     PostgresSearchEngine (BM25/substring/vector)
│   │       ├── bm25.py               #     tsvector BM25 search
│   │       ├── vector.py             #     pgvector HNSW cosine search
│   │       ├── vector_validation.py  #     Runtime vector readiness check
│   │       ├── jieba_recall.py       #     Jieba-tokenized BM25
│   │       ├── substring_recall.py   #     Bidirectional substring recall
│   │       ├── import_writer.py      #     BulkImportAdapter (psycopg batch writer)
│   │       └── _db/                  #     PRIVATE — models, connection, schema, URL,
│   │           │                      #       context, resources, embeddings, tsvector
│   │           └── sql_assets/       #     Packaged DDL/seed/migration SQL (wheel)
│   │
│   ├── contracts/                    # Interface contracts & shared types (ZERO external deps)
│   │   ├── protocols.py              #   TermReader, TermSearchEngine, TermWriter protocols
│   │   ├── types.py                  #   Frozen dataclass/Pydantic types (20+)
│   │   ├── intent_types.py           #   Intent domain shared types (safe for retrieval/)
│   │   ├── text.py                   #   Tokenizer, StopwordProvider protocols
│   │   └── rrf.py                    #   RRF fusion algorithm
│   │
│   ├── i18n/                         # Internationalization (pure data, no logic)
│   │   └── prompts.py                #   zh_CN/en_US LLM prompts, labels, annotations
│   │
│   ├── ingestion/                    # Knowledge package import & generation
│   │   ├── owl_import/               #   OWL knowledge package import
│   │   │   └── importer/             #     executor, runner, precheck, parser, converter,
│   │   │       ├── writer/           #       per-entity batch writers (7 entities)
│   │   │       └── notifier.py       #       Import notification callback
│   │   └── owl_generate/             #   DB schema → OWL import package generator
│   │       ├── generator.py          #     Main orchestration
│   │       ├── models.py             #     Config dataclasses
│   │       ├── schema_reader.py      #     DB schema reader
│   │       └── renderers/            #     OWL XML renderers (6 entity renderers)
│   │
│   ├── intent/                       # Intent understanding & clarification
│   │   ├── __init__.py               #   Exports 26 symbols (public API surface)
│   │   ├── disambiguation.py         #   Term disambiguation & path graph
│   │   ├── llm_utils.py              #   LLM event emitter
│   │   ├── score_update.py           #   Term score update (batch + async)
│   │   ├── types.py                  #   Intent domain types (StreamEvent, SlotResult, etc.)
│   │   └── clarification/            #   Multi-turn clarification subsystem
│   │       ├── api.py                #     analyze/format clarification entry points
│   │       ├── _expand_query.py      #     Query expansion
│   │       ├── extract.py            #     Entity extraction
│   │       ├── format.py             #     Clarification formatting
│   │       ├── models.py             #     Clarification domain models
│   │       ├── postprocess.py        #     Normalization + confirmed synonym persistence
│   │       ├── _patch.py             #     Structured input patching
│   │       ├── _pre_resolve.py       #     Pre-resolution helpers
│   │       ├── _merge.py             #     Result merge helpers
│   │       ├── confirm/              #     LLM confirmation (_main, _cc, _context, _retry)
│   │       ├── cartesian/            #     Cartesian expansion (_expand, _paradigm)
│   │       └── merge/                #     Result merge (_hints, _cc_normalize)
│   │
│   └── retrieval/                    # Knowledge retrieval & search
│       ├── term_search.py            #   Delegation layer → adapters reader
│       ├── orchestration.py          #   search_terms_with_fallback (exact → BM25)
│       ├── mention_matching.py       #   Mention-level term matching (exact/rapidfuzz)
│       ├── name_cache.py             #   UserNameCache (term name index)
│       ├── candidate_search.py       #   Candidate search with name_id support
│       ├── typed_recall.py           #   Typed multi-recall with session
│       ├── _recall.py                #   Unified + vector-only recall for clarification
│       ├── _recall_common.py         #   Shared recall utilities
│       ├── rrf.py                    #   RRF fusion
│       ├── dimension_values.py       #   Dimension value resolver
│       ├── owl_relation_resolver.py  #   OWL relation traversal
│       ├── recall/                   #   Multi-strategy recall engine
│       │   ├── _orchestrator.py      #     Recall orchestration
│       │   ├── _fusion.py            #     Strategy fusion
│       │   ├── _scope.py             #     Scope-based recall
│       │   ├── _paths.py             #     Path-based recall
│       │   ├── _models.py            #     Recall domain models
│       │   └── _sql.py               #     SQL generation
│       ├── embedding/                #   OpenAI-compatible embedding service
│       └── tokenizers/               #   Chinese (jieba) & English (whitespace) tokenizers
│
├── db/                               # Source SQL assets (see db/AGENTS.md for details)
│   ├── ddl/knowledge/                #   Complete schema DDL (00..99 order)
│   ├── seed/knowledge/               #   Built-in seed data (idempotent)
│   ├── migrations/                   #   Incremental schema upgrades
│   ├── data_fixes/                   #   Manual data synchronization/fixes
│   ├── scripts/                      #   Operational Python scripts (apply, verify, backfill, migrate)
│   ├── er/                           #   Mermaid ER source
│   └── docs/                         #   Design notes
│
├── tests/                            # pytest tests by domain
│   ├── intent/                       #   Intent/clarification tests (conftest.py with markers)
│   ├── importer/                     #   OWL converter tests
│   ├── provider/                     #   Provider facade tests
│   ├── test_importer.py              #   Importer integration
│   └── test_owl_gen_multiview.py     #   OWL generation tests
│
└── scripts/manual/                   # Manual/eval scripts (print allowed by ruff override)
```

## Modules that changed location (2026-05 restructure)

These old paths no longer exist — use the new ones:

| Old Path | New Path | What Changed |
|----------|----------|-------------|
| `intent/cache.py` | `retrieval/name_cache.py` | UserNameCache moved to retrieval |
| `intent/matching.py` | `retrieval/mention_matching.py` | Mention matching moved to retrieval |
| `intent/recall/` | `retrieval/recall/` | Recall engine moved to retrieval |
| `intent/clarification/_recall.py` | `retrieval/_recall.py` | Clarification recall moved to retrieval |
| `intent/service.py` | _(removed)_ | `*WithSession` facade no longer exists |
| `file_store/` | _(removed)_ | Directory never had implementation; now gone |

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Public API entry | `src/datacloud_knowledge/provider.py` | 6 functions: alias resolution, term search, clarification, prop queries |
| CLI entry | `src/datacloud_knowledge/cli.py` | `datacloud-knowledge` console script (6 commands) |
| DB access factories | `src/datacloud_knowledge/adapters/__init__.py` | `create_reader()`, `create_engine()`, `create_writer()`, `create_bulk_importer()`, `store_clarification_results()` |
| Schema lifecycle | `src/datacloud_knowledge/adapters/__init__.py` → `opengauss/_db/schema.py` | `ensure_schema()`, `verify_schema()` |
| DB URL/schema resolution | `src/datacloud_knowledge/adapters/opengauss/_db/url.py` | Parses JDBC/libpq/env URLs |
| DB connection/session | `src/datacloud_knowledge/adapters/opengauss/_db/connection.py` | SQLAlchemy session factory |
| ORM models | `src/datacloud_knowledge/adapters/opengauss/_db/models.py` | PRIVATE — do not import from non-adapter code |
| Search recall (BM25, vector, substring) | `src/datacloud_knowledge/adapters/opengauss/engine.py` | TermSearchEngine implementation |
| Term reader (all queries) | `src/datacloud_knowledge/adapters/opengauss/reader.py` | TermReader implementation |
| Term writer (all writes) | `src/datacloud_knowledge/adapters/opengauss/writer.py` | TermWriter implementation |
| Bulk import writer | `src/datacloud_knowledge/adapters/opengauss/import_writer.py` | Psycopg batch writer for OWL import |
| Shared types | `src/datacloud_knowledge/contracts/types.py` | All frozen dataclasses, Pydantic models, type aliases |
| Intent domain types | `src/datacloud_knowledge/contracts/intent_types.py` | Types shared between intent/ and retrieval/ |
| Interface protocols | `src/datacloud_knowledge/contracts/protocols.py` | TermReader, TermSearchEngine, TermWriter protocols |
| RRF fusion | `src/datacloud_knowledge/contracts/rrf.py` | Reciprocal Rank Fusion |
| Tokenizer protocols | `src/datacloud_knowledge/contracts/text.py` | Tokenizer, StopwordProvider |
| Term search orchestration | `src/datacloud_knowledge/retrieval/orchestration.py` | Exact match → BM25 fallback |
| Term search delegation | `src/datacloud_knowledge/retrieval/term_search.py` | search_terms_by_type, resolve_field_aliases, etc. |
| Mention matching | `src/datacloud_knowledge/retrieval/mention_matching.py` | Exact/rapidfuzz/bm25 mention → term matching |
| UserNameCache | `src/datacloud_knowledge/retrieval/name_cache.py` | Term name index with user alias support |
| Typed recall | `src/datacloud_knowledge/retrieval/typed_recall.py` | Typed multi-recall with session |
| Clarification recall | `src/datacloud_knowledge/retrieval/_recall.py` | Unified + vector-only recall |
| Recall engine | `src/datacloud_knowledge/retrieval/recall/_orchestrator.py` | Multi-strategy recall orchestration |
| Embedding service | `src/datacloud_knowledge/retrieval/embedding/service.py` | OpenAI-compatible embedding API |
| Chinese tokenizer | `src/datacloud_knowledge/retrieval/tokenizers/chinese.py` | Jieba-based |
| English tokenizer | `src/datacloud_knowledge/retrieval/tokenizers/english.py` | Whitespace-based |
| Intent disambiguation | `src/datacloud_knowledge/intent/disambiguation.py` | Candidate disambiguation & path graph |
| Clarification analysis | `src/datacloud_knowledge/intent/clarification/api.py` | `analyze_query_clarification()` entry |
| Clarification LLM confirmation | `src/datacloud_knowledge/intent/clarification/confirm/_main.py` | LLM-based term confirmation |
| Clarification Cartesian expansion | `src/datacloud_knowledge/intent/clarification/cartesian/_expand.py` | Condition Cartesian product |
| Clarification postprocess | `src/datacloud_knowledge/intent/clarification/postprocess.py` | Normalization + synonym persistence |
| Score update | `src/datacloud_knowledge/intent/score_update.py` | Term score batch/async update |
| OWL import executor | `src/datacloud_knowledge/ingestion/owl_import/importer/executor.py` | Called by CLI `import-terms` |
| OWL import pipeline | `src/datacloud_knowledge/ingestion/owl_import/importer/runner.py` | precheck → executor → callback |
| OWL package generator | `src/datacloud_knowledge/ingestion/owl_generate/generator.py` | DB schema → OWL XML package |
| Internationalization | `src/datacloud_knowledge/i18n/prompts.py` | zh_CN/en_US prompts, labels |
| SQL assets (source) | `db/ddl/knowledge/`, `db/seed/knowledge/`, `db/migrations/` | Packaged into wheel at `adapters/opengauss/_db/sql_assets/` |
| DB operational scripts | `db/scripts/` | apply, verify, backfill, migrate (use `python db/scripts/*.py`) |
| ER diagram | `db/er/whale_datacloud.mmd` | Mermaid ER source |

## CODE MAP

### Adapter factories (`adapters/__init__.py`)

| Symbol | Role |
|--------|------|
| `create_reader()` | Factory for TermReader instances |
| `create_engine()` | Factory for TermSearchEngine instances (accepts optional `session`) |
| `create_writer()` | Factory for TermWriter instances (accepts optional `session`) |
| `create_bulk_importer()` | Factory for BulkImportAdapter (psycopg batch writer) |
| `store_clarification_results()` | Persist clarification results to DB (self-managed session) |
| `ensure_schema()` | Schema lifecycle management |
| `verify_schema()` | Verify core tables exist |
| `backfill_tsvector()` | Jieba tsvector backfill |
| `backfill_embeddings()` | Embedding vector backfill |

### OpenGauss backend (`adapters/opengauss/`)

| Symbol | Location | Role |
|--------|----------|------|
| `PostgresTermReader` | `reader.py` | TermReader implementation |
| `PostgresTermWriter` | `writer.py` | TermWriter implementation |
| `PostgresSearchEngine` | `engine.py` | TermSearchEngine implementation |
| `BulkImportAdapter` | `import_writer.py` | Psycopg batch import writer |
| `DatabaseContext` | `_db/context.py` | Transaction-local search_path |

### Contracts (`contracts/`)

| Symbol | Location | Role |
|--------|----------|------|
| `TermReader` | `protocols.py` | Read-side interface |
| `TermSearchEngine` | `protocols.py` | Search-side interface |
| `TermWriter` | `protocols.py` | Write-side interface |
| `TagFilter` | `types.py` | Tag filtering model |
| `SearchTermsResult` | `types.py` | Paginated search result |
| `FieldResolutionResult` | `types.py` | Field alias resolution result |

### Public API (`provider.py`)

| Symbol | Role |
|--------|------|
| `resolve_field_aliases()` | Field alias resolution |
| `search_terms_by_type()` | Typed term search |
| `prepare_query_clarification()` | Clarification analysis |
| `finalize_query_clarification()` | Clarification finalize |
| `get_object_props_by_code()` | Object properties query |
| `get_prop_enum_values()` | Property enum values query |

### Retrieval keys

| Symbol | Location | Role |
|--------|----------|------|
| `search_terms_with_fallback()` | `orchestration.py` | Exact → BM25 orchestration |
| `match_mentions()` | `mention_matching.py` | Mention → term matching |
| `UserNameCache` | `name_cache.py` | Term name index (was in `intent/cache.py`) |
| `typed_multi_recall_with_session()` | `typed_recall.py` | Typed multi-recall |

### Intent keys

| Symbol | Location | Role |
|--------|----------|------|
| `analyze_query_clarification()` | `clarification/api.py` | Clarification analysis core |
| `disambiguate()` | `disambiguation.py` | Term disambiguation |
| `build_shortest_path_tree()` | `disambiguation.py` | Path graph construction |
| `update_score()` / `batch_update_scores()` | `score_update.py` | Term score update |
| `expand_query()` | `clarification/_expand_query.py` | Query expansion |

### Ingestion keys

| Symbol | Location | Role |
|--------|----------|------|
| `run()` | `owl_import/importer/executor.py` | OWL import executor |
| `generate()` | `owl_generate/generator.py` | OWL package generator |

## RETRIEVAL LOGIC

### Clarification Pipeline (6 steps)

`analyze_query_clarification()` in `intent/clarification/api.py` orchestrates:

```
Step 1  术语提取       extract.py          → ExtractedTerm[] (按ktype分类: select/whereKey/whereValue/...)
Step 2  字段预解析     _pre_resolve.py      → resolve_field_aliases_with_names() 确认已知字段
                                            → get_prop_enum_values() 查枚举值, 尝试精确匹配 whereValue
Step 3  知识召回       _recall.py           → unified_recall() 对未解析术语执行多路召回
                                            → field/vlue terms 分治, 各自使用不同 scope layers
Step 4a 主结构LLM确认  confirm/_main.py     → format_main_confirm_context() + llm_confirm_main()
Step 4b 条件LLM确认    confirm/_main.py     → 逐条 complex_condition 的 LLM 确认
Step 5  结果合并       merge/_llm_confirm.py → 合并 pre-resolve + main + cc 结果
Step 6  构建paradigm   cartesian/_paradigm.py → 生成前端 paradigmList + KnowledgeMeta
```

### Recall Architecture

**4 路并发召回** (`recall/_paths.py`), 结果经 RRF 融合 (`recall/_fusion.py`):

| 路径 | 文件 | 机制 | 适用场景 |
|------|------|------|----------|
| BM25 AND | `_paths.py:_batch_bm25_and` | 单字 AND tsquery (`黄 & 总`) | 精确匹配 |
| Jieba BM25 | `_paths.py:_batch_jieba_bm25` | jieba 分词后 AND tsquery | 中文分词匹配 |
| Substring | `_paths.py:_batch_substring` | 双向子串包含 (keyword↔term_name) | 模糊匹配 |
| Vector | `_paths.py:_batch_vector` | pgvector HNSW cosine 相似度 | 语义匹配 (英文标识符→中文名称) |

**单字兜底** (`recall/_fusion.py:_add_single_char_fallback_results`):
当 bm25_and / jieba / substring 三条文本路径全部为空时，退化到 CJK 单字 OR (`黄 | 总`)，捕捉人名、地名等短文本的弱候选。

### Type Filtering (KTYPE_CATEGORY_MAP)

`retrieval/_recall_common.py:29` 按术语类型约束召回候选的 `type_category`:

| ktype | 允许的 type_category | 说明 |
|-------|---------------------|------|
| `select`, `groupBy`, `whereKey`, `orderBy` | `{3}` | 只搜本体术语 (prop/object/view) |
| `whereValue` | `{1, 2}` | 只搜列表术语(1)和字典术语(2) — 维度值 |

whereValue 不搜 category 3 (本体术语)，因为维度值是企业名、用户名、状态等具体数据，不是结构定义。

### Scope Recall Layers

`retrieval/_recall.py:build_scope_recall_layers()` 返回 `(field_layers, value_layers)` 两个独立的 scope 栈。
`unified_recall()` 按 ktype 分流: whereValue 使用 value_layers, 其余 (select/whereKey/groupBy/orderBy) 使用 field_layers。

**field_layers** (字段术语 — select/whereKey/groupBy/orderBy):

| # | 来源 | 权重 | 标签 | 说明 |
|---|------|------|------|------|
| 1 | `ontology_code` | 1.0 | `ontology` | 当前查询的本体 (如 `by_rd_task`) |

字段名仅在本体内搜索，不跨本体，避免其他本体的 prop 污染候选列表。

**value_layers** (维度值 — whereValue):

| # | 来源 | 权重 | 标签 | 说明 |
|---|------|------|------|------|
| 1 | `ontology_code` | 1.0 | `ontology` | 当前查询的本体 |
| 2 | `_collect_view_included_objects()` | 0.8 | `included_object` | **仅当 ontology_code 是 view 时**：查 view 的 BUSINESS 关系 target 为 object 的项（如"研发管理视图_包含_用户信息表" → po_users），将其 scope 加入 value_layers，让 view 能搜到包含对象下的 value term |
| 3 | `_collect_joinkey_related_objects()` | 0.7 | `joinkey_object` | 仅当 confirmed field 匹配 joinkeys.sourceField 才加入 |

**view → included_objects 解析** (`_recall.py:_collect_view_included_objects`):
当 ontology_code 是 view 时，view 通过 BUSINESS 关系"包含"若干底层对象（如 `scene_rd_management` 包含 `by_customer`, `by_rd_task`, `po_users` 等）。这些对象的 HAS_FIELD relation 下才有 value term（`search_scope = '{}'`）的子项。`_collect_view_included_objects()` 不加 joinkey 过滤，全部纳入 value_layers，让 value term 能通过包含对象的 scope 被搜到。

**字段级 joinkey 扩展** (`_recall.py:_collect_joinkey_related_objects`):
当 confirmed field (如 `handler_user_id`) 的值存储在另一个 ontology object (如 `po_users`) 时，从 `term_relation.ext_attrs` 的 joinkeys 读取字段级关联关系。只有 `confirmed_field ∈ joinkeys.sourceField` 时才将目标 object 纳入 scope。不会盲目把所有 BUSINESS 关联对象都加进来（如 `by_opportunity → by_project` 不会因为 `opp_name` 字段而把 `by_project` 加入 scope）。

```
by_rd_task ──(BUSINESS, handler_user_id→user_id)──→ po_users
                                                       │
                                        po_users.user_name → 黄总、李总...
```

**分层召回流程** (`recall/_scope.py:_typed_multi_recall_layered`):
1. unified_recall 将术语按 ktype 分为 field_terms / value_terms
2. 各自使用对应的 scope layers 执行 4 路并发召回 → RRF 融合
3. 若某 keyword 在所有 layer 的文本路径都为空，追加单字兜底

### Scope Filtering SQL

`adapters/opengauss/engine.py:_build_effective_scope_clause()` 生成 scope 过滤 SQL:

- `strict=True` (本体术语 whereKey 等): 只匹配 `search_scope` 明确指定当前 scope 的 term
- `strict=False` (维度值 whereValue): 额外允许 `search_scope='{}'` 的 term, 只要其所属对象在当前 ontology 的 root subtree 下

### Data Flow: Query → Clarification Result

```
用户查询 "黄总作为处理人"
        │
  structured_query: {filters: [{field: "handler_user_id", value: "黄总"}]}
        │
  extract → whereKey="handler_user_id" (vector_only=True)
            whereValue="黄总" (search_enabled=True)
        │
  pre_resolve → resolve_field_aliases("handler_user_id", "by_rd_task")
                → 确认: handler_user_id → 处理人用户编码(ref: po_users.user_code)
                → get_prop_enum_values("handler_user_id") → [] (枚举值为空)
                → "黄总" 精确匹配失败 → unresolved
        │
  build_scope_layers → field_layers = [by_rd_task]
                      → _collect_joinkey_related_objects("by_rd_task", ["handler_user_id"])
                      → joinkeys: handler_user_id ∈ sourceFields → +po_users
                      → value_layers = [by_rd_task, po_users(0.7)]
        │
  unified_recall → field terms (whereKey) → field_layers=[by_rd_task]
                  → value terms (whereValue) → value_layers=[by_rd_task, po_users]
                  → "黄总" whereValue: 4路召回 + RRF融合 → [候选列表, 含 po_users 的值]
        │
  LLM confirm → sees candidates from po_users scope
               → returns ClarifyItem(keyword="黄总", candidates=[...])
        │
  paradigm → fieldRecall=["处理人用户编码(...)"], valueRecall=[候选值]
            → needs_clarification=true ✅
```

## CONVENTIONS

### Layer import constraints (hard rule)

- **Non-adapter code MUST NOT import SQLAlchemy or psycopg** — all DB access goes through `adapters` factories.
- **Non-adapter code MUST NOT import ORM models** — `adapters/opengauss/_db/models.py` is private.
- **Non-adapter code MUST NOT import session factories** — `adapters/opengauss/_db/connection.py` is private.
- **Non-adapter code MUST NOT import from `adapters/opengauss/_db/` directly** — only `adapters/__init__.py` exposes public functions.
- **Module path correctness** — `import_module` paths are not statically checked by ruff. Verify paths manually.

### Module placement rules

- **Recall/retrieval logic lives in `retrieval/`** — moved from `intent/recall/` and `intent/clarification/_recall.py` during 2026-05 restructure. Do not add new recall code under `intent/`.
- **Mention matching lives in `retrieval/mention_matching.py`** — not `intent/matching.py` (stale path).
- **Name cache lives in `retrieval/name_cache.py`** — not `intent/cache.py` (stale path).
- **`contracts/intent_types.py`** — intent domain types shared between `retrieval/` and `intent/`. When retrieval modules need intent-specific types, add them here, not via reverse-dependency.

### General conventions

- **Version mismatch**: `pyproject.toml` version is `0.1.0`; runtime `__version__` is `0.2.0`. Check both before release/version work.
- **`intent/__init__.py` exports 26 symbols** — this is the public API surface. Preserve existing names unless coordinating downstream changes with `datacloud-analysis`.
- **DB SQL should use bare table names** — schema is injected through `DatabaseContext` / connection `search_path`. Only information_schema or schema-management code may use schema-qualified names.
- **Backend selection**: Defaults to `"opengauss"`. Override via `DATACLOUD_KNOWLEDGE_BACKEND` env var or explicit parameter. Only `opengauss` is currently registered.
- **`contracts/` has zero external dependencies** — pure protocols and dataclasses. Safe to import from anywhere.
- **Ruff per-file ignores**: Root config has package-specific ignores for legacy complexity and dynamic SQL. Do not add new ignores without narrowing them to the smallest possible file.

## TESTS

Run from repo root:

```bash
uv run pytest packages/datacloud-knowledge/tests                    # All tests
uv run pytest packages/datacloud-knowledge/tests -m db_integration  # DB integration tests
uv run pytest packages/datacloud-knowledge/tests/intent             # Intent-only tests
```

| Area | Tests |
|------|-------|
| Intent/clarification | `tests/intent/test_clarification*.py` (4 files) + `test_clarification_cc_consistency.py` + `test_clarification_confirm_retry.py` + `test_clarification_postprocess.py` |
| Intent/disambiguation | `tests/intent/test_disambiguation.py` |
| Intent/matching | `tests/intent/test_matching.py` |
| Intent/recall | `tests/intent/test_typed_recall.py`, `test_scope_recall_clause.py`, `test_batch_recall_sql_compat.py`, `test_scope_user_sql_compat.py` |
| Intent/aliases | `tests/intent/test_resolve_field_aliases.py` |
| Intent service | `tests/intent/test_service_vector_toggle.py` |
| Importer | `tests/test_importer.py`, `tests/importer/test_owl_converter.py` |
| OWL generator | `tests/test_owl_gen_multiview.py` |
| Provider facade | `tests/provider/test_provider.py` |

**Test configuration:**
- `asyncio_mode = "auto"` (set in package `pyproject.toml`)
- `conftest.py` at `tests/intent/` registers `intent` and `db_integration` markers
- Root pytest config only references older `tests/db`/`tests/ontology` paths — prefer package-local commands above
- DB integration tests require `DATACLOUD_DB_*` env vars or `.env` file (see `tests/.env.example`)

## COMMANDS

### Development (from repo root)

```bash
uv sync
uv run ruff format packages/datacloud-knowledge
uv run ruff check packages/datacloud-knowledge
uv run mypy packages/datacloud-knowledge/src/datacloud_knowledge
uv run pytest packages/datacloud-knowledge/tests
```

### CLI commands

```bash
uv run --package datacloud-knowledge datacloud-knowledge --help
uv run --package datacloud-knowledge datacloud-knowledge ensure-schema --schema whale_datacloud
uv run --package datacloud-knowledge datacloud-knowledge import-terms ./path/to/package --schema whale_datacloud
uv run --package datacloud-knowledge datacloud-knowledge backfill-tsvector --schema whale_datacloud
uv run --package datacloud-knowledge datacloud-knowledge backfill-embeddings --schema whale_datacloud
uv run --package datacloud-knowledge datacloud-knowledge verify-schema --schema whale_datacloud
uv run --package datacloud-knowledge datacloud-knowledge bootstrap ./path/to/package --schema whale_datacloud
```

### DB operational scripts (from package root)

```bash
python db/scripts/apply_whale_datacloud.py              # DDL then seed
python db/scripts/apply_whale_datacloud.py --seed-only  # Seed only
python db/scripts/verify_whale_datacloud.py             # Verify table structure
python db/scripts/backfill_jieba_tsvector.py --help     # Jieba tsvector backfill
python db/scripts/migrate_term_name_embeddings.py --help # Embedding migration
```

The CLI commands above are the preferred interface for schema management. DB scripts remain available for backward compatibility. See `db/AGENTS.md` for the full DB asset guide.

## ENVIRONMENT

| Variable | Purpose |
|----------|---------|
| `DATACLOUD_DB_URL` | JDBC-style DB URL (e.g., `jdbc:opengauss://host:port/db?currentSchema=whale_datacloud`) |
| `DATACLOUD_DB_HOST`, `DATACLOUD_DB_PORT`, `DATACLOUD_DB_DATABASE` | Split DB connection params (alternative to DB_URL) |
| `DATACLOUD_DB_USER`, `DATACLOUD_DB_PASSWORD` | DB credentials |
| `DATACLOUD_DB_SCHEMA` | Target schema; defaults to `whale_datacloud` |
| `DATACLOUD_KNOWLEDGE_BACKEND` | Backend selection (default: `"opengauss"`) |
| `DATACLOUD_INTENT_DEBUG` | Enables intent package DEBUG logging |
| `DATACLOUD_INTENT_ENABLE_VECTOR` | Toggles vector recall in intent service |
| `DATACLOUD_KNOWLEDGE_BACKFILL_BATCH_SIZE` | Jieba tsvector backfill batch size |
| `DATACLOUD_SOURCE_DB_*` | Source DB for embedding migration script |
| `DATACLOUD_ENABLE_INTEGRATION_TESTS` | Set to `1` to enable DB integration tests |

See `.env.example` and `tests/.env.example` for templates.

## ANTI-PATTERNS

- **Do NOT import SQLAlchemy or psycopg outside `adapters/`** — use factory functions.
- **Do NOT import ORM models directly** — `adapters/opengauss/_db/models.py` is private.
- **Do NOT import from `adapters/opengauss/_db/` directly** — only `adapters/__init__.py` exposes public functions.
- **Do NOT use stale module paths** — `intent/cache.py`, `intent/service.py`, `intent/matching.py`, `intent/recall/`, `file_store/` no longer exist. Use the new paths documented above.
- **Do NOT hard-code `whale_datacloud.` in SQL** — use `DatabaseContext` / connection `search_path`.
- **Do NOT use wildcard imports** — except in existing compatibility shim files with explicit ruff exceptions.
- **Do NOT use unqualified `# type: ignore`** — must include error code (enforced by root ruff/mypy).
- **Do NOT add production `print()` calls** — only `scripts/manual/*.py` has a ruff override for this.
- **Do NOT bypass importer precheck** — OWL import failure must roll back the whole import as a single transaction.
- **Do NOT split importer writes across independent transactions** — all entity writers share one transaction context.

## NOTES

- **Architecture restructure (2026-05)**: Old modules were reorganized. The recall engine moved from `intent/recall/` → `retrieval/recall/`. Matching and cache moved to `retrieval/`. See "Modules that changed location" table above.
- **`db/` is still present** as source SQL assets (DDL, seed, migrations, scripts). These are packaged into the wheel at `adapters/opengauss/_db/sql_assets/`. See `db/AGENTS.md` for the full DB asset guide.
- **Only `opengauss` backend is registered** — the adapter factory supports backend selection by env var, but no MySQL or other backends are implemented yet.
- **LSP/Pyright baseline**: Pre-existing diagnostics in `adapters/opengauss/bm25.py` and some legacy shims exist. Treat them as baseline unless your change touches those paths.
- **`TODO(ontology)`**: ontology_code filtering in clarification is not complete.
- **`intent/__init__.py`** exports a public API surface (~26 symbols). Do not rename public exports without coordinating with downstream `datacloud-analysis` consumers.
