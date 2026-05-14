# AGENTS.md — datacloud-knowledge

**Generated:** 2026-05-14
**Package:** datacloud-knowledge (workspace member of by-datacloud)
**Python:** >=3.12
**Toolchain:** uv + ruff + mypy (inherited from root workspace)

## OVERVIEW

`datacloud-knowledge` is the knowledge SDK for term retrieval, ontology import/export, intent disambiguation, and NL-to-knowledge-query support. It bridges the gap between "what users say" and "what the system understands."

**Architecture (post-restructure):** Six top-level modules with strict layering:

```
provider.py (public API facade)
    ├── adapters/     ← DB access (factory + OpenGauss backend)
    ├── contracts/    ← interfaces & shared types (no deps)
    ├── i18n/         ← LLM prompt i18n
    ├── intent/       ← recall, disambiguation, clarification
    └── retrieval/    ← term search, embeddings, tokenizers

cli.py → adapters/ + ingestion/
```

## STRUCTURE

```text
packages/datacloud-knowledge/
├── pyproject.toml                 # Package metadata (version: 0.1.0), console_scripts
├── src/datacloud_knowledge/
│   ├── __init__.py                # Exports __version__ = "0.2.0"
│   ├── cli.py                     # CLI entry: datacloud-knowledge (6 commands)
│   ├── provider.py                # Public API facade (6 functions)
│   │
│   ├── adapters/                  # DB access layer (factory + registry)
│   │   ├── __init__.py            #   Factories: create_reader/engine/writer
│   │   │                          #   Schema mgmt: ensure_schema, verify_schema
│   │   │                          #   Backfill: backfill_tsvector, backfill_embeddings
│   │   │                          #   Bulk import: create_bulk_importer
│   │   └── opengauss/             #   OpenGauss/PostgreSQL backend (ONLY registered backend)
│   │       ├── reader.py          #     PostgresTermReader (TermReader impl)
│   │       ├── writer.py          #     PostgresTermWriter (TermWriter impl)
│   │       ├── engine.py          #     PostgresSearchEngine (BM25/substring/vector)
│   │       ├── bm25.py            #     tsvector BM25 search
│   │       ├── vector.py          #     pgvector HNSW cosine search
│   │       ├── vector_validation.py #   Runtime vector readiness check
│   │       ├── jieba_recall.py    #     Jieba-tokenized BM25
│   │       ├── substring_recall.py #    Bidirectional substring recall
│   │       ├── import_writer.py   #     BulkImportAdapter (psycopg batch writer)
│   │       └── _db/               #     PRIVATE — ORM models, connection, schema, URL,
│   │           │                   #       context, resources, embeddings, tsvector
│   │           └── sql_assets/    #     Packaged DDL/seed/migration SQL
│   │
│   ├── contracts/                 # Interface contracts & shared types (ZERO external deps)
│   │   ├── protocols.py           #   TermReader (18 methods), TermSearchEngine, TermWriter
│   │   ├── types.py               #   20+ frozen dataclass/Pydantic types
│   │   ├── text.py                #   Tokenizer, StopwordProvider protocols
│   │   └── rrf.py                 #   RRF fusion algorithm
│   │
│   ├── i18n/                      # Internationalization (pure data, no logic)
│   │   └── prompts.py             #   zh_CN/en_US LLM prompts, labels, annotations
│   │
│   ├── ingestion/                 # Knowledge package import & generation
│   │   ├── owl_import/            #   OWL knowledge package import
│   │   │   └── importer/          #   executor, runner, precheck, parser, converter,
│   │   │       ├── writer/        #     per-entity batch writers (7 entities)
│   │   │       └── notifier.py    #     Import notification callback
│   │   └── owl_generate/          #   DB schema → OWL import package generator
│   │       ├── generator.py       #     Main orchestration
│   │       ├── models.py          #     Config dataclasses
│   │       ├── schema_reader.py   #     DB schema reader
│   │       └── renderers/         #     OWL XML renderers (6 entity renderers)
│   │
│   ├── intent/                    # Intent understanding & clarification
│   │   ├── __init__.py            #   Exports 56+ symbols (legacy API surface)
│   │   ├── service.py             #   *WithSession functions for external consumers
│   │   ├── disambiguation.py      #   Term disambiguation & path graph
│   │   ├── matching.py            #   Mention matching
│   │   ├── cache.py               #   UserNameCache
│   │   ├── llm_utils.py           #   LLM event emitter
│   │   ├── recall/                #   Multi-strategy recall (_orchestrator, _fusion, _scope, _paths)
│   │   └── clarification/         #   Multi-turn clarification
│   │       ├── api.py             #     analyze/format clarification entry points
│   │       ├── confirm/           #     LLM confirmation (_main, _cc, _context, _retry)
│   │       ├── cartesian/         #     Cartesian expansion (_expand, _paradigm)
│   │       └── merge/             #     Result merge (_hints, _pre_resolve, _cc_normalize)
│   │
│   └── retrieval/                 # Knowledge retrieval & search
│       ├── term_search.py         #   Delegation layer → adapters reader
│       ├── orchestration.py       #   search_terms_with_fallback (exact → BM25)
│       ├── rrf.py                 #   RRF fusion
│       ├── dimension_values.py    #   Dimension value resolver
│       ├── owl_relation_resolver.py # OWL relation traversal
│       ├── embedding/             #   OpenAI-compatible embedding service
│       └── tokenizers/            #   Chinese (jieba) & English (whitespace) tokenizers
│
├── db/                            # Source SQL assets (see db/AGENTS.md for details)
│   ├── ddl/knowledge/             #   Complete schema DDL (00..99 order)
│   ├── seed/knowledge/            #   Built-in seed data (idempotent)
│   ├── migrations/                #   Incremental schema upgrades
│   ├── scripts/                   #   Operational Python scripts (apply, verify, backfill, migrate)
│   ├── er/                        #   Mermaid ER source
│   └── docs/                      #   Design notes
│
├── tests/                         # pytest tests by domain
│   ├── intent/                    #   Intent/clarification tests (conftest.py with markers)
│   ├── importer/                  #   OWL converter tests
│   ├── provider/                  #   Provider facade tests
│   ├── test_importer.py           #   Importer integration
│   └── test_owl_gen_multiview.py  #   OWL generation tests
│
└── scripts/manual/                # Manual/eval scripts (print allowed by ruff override)
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Public API entry | `src/datacloud_knowledge/provider.py` | 6 functions: alias resolution, term search, clarification, prop queries |
| CLI entry | `src/datacloud_knowledge/cli.py` | `datacloud-knowledge` console script (ensure-schema, import-terms, backfill-*, bootstrap) |
| DB access factories | `src/datacloud_knowledge/adapters/__init__.py` | `create_reader()`, `create_engine()`, `create_writer()`, `create_bulk_importer()` |
| Schema lifecycle | `src/datacloud_knowledge/adapters/__init__.py` → `opengauss/_db/schema.py` | `ensure_schema()`, `verify_schema()` |
| DB URL/schema resolution | `src/datacloud_knowledge/adapters/opengauss/_db/url.py` | Parses JDBC/libpq/env URLs |
| DB connection/session | `src/datacloud_knowledge/adapters/opengauss/_db/connection.py` | SQLAlchemy session factory |
| ORM models | `src/datacloud_knowledge/adapters/opengauss/_db/models.py` | PRIVATE — do not import from non-adapter code |
| Search recall (BM25, vector, substring) | `src/datacloud_knowledge/adapters/opengauss/engine.py` | TermSearchEngine implementation |
| Term reader (all queries) | `src/datacloud_knowledge/adapters/opengauss/reader.py` | TermReader implementation (18 query methods) |
| Term writer (all writes) | `src/datacloud_knowledge/adapters/opengauss/writer.py` | TermWriter implementation (8 write methods) |
| Bulk import writer | `src/datacloud_knowledge/adapters/opengauss/import_writer.py` | Psycopg batch writer for OWL import |
| Shared types | `src/datacloud_knowledge/contracts/types.py` | All frozen dataclasses, Pydantic models, type aliases |
| Interface protocols | `src/datacloud_knowledge/contracts/protocols.py` | TermReader, TermSearchEngine, TermWriter protocols |
| RRF fusion | `src/datacloud_knowledge/contracts/rrf.py` | Reciprocal Rank Fusion |
| Tokenizer protocols | `src/datacloud_knowledge/contracts/text.py` | Tokenizer, StopwordProvider |
| Term search orchestration | `src/datacloud_knowledge/retrieval/orchestration.py` | Exact match → BM25 fallback |
| Term search delegation | `src/datacloud_knowledge/retrieval/term_search.py` | search_terms_by_type, resolve_field_aliases, etc. |
| Embedding service | `src/datacloud_knowledge/retrieval/embedding/service.py` | OpenAI-compatible embedding API |
| Chinese tokenizer | `src/datacloud_knowledge/retrieval/tokenizers/chinese.py` | Jieba-based |
| English tokenizer | `src/datacloud_knowledge/retrieval/tokenizers/english.py` | Whitespace-based |
| Intent recall | `src/datacloud_knowledge/intent/recall/_orchestrator.py` | Multi-strategy recall orchestration |
| Intent disambiguation | `src/datacloud_knowledge/intent/disambiguation.py` | Candidate disambiguation & path graph |
| Clarification analysis | `src/datacloud_knowledge/intent/clarification/api.py` | `analyze_query_clarification()` entry |
| Clarification LLM confirmation | `src/datacloud_knowledge/intent/clarification/confirm/_main.py` | LLM-based term confirmation |
| Clarification Cartesian expansion | `src/datacloud_knowledge/intent/clarification/cartesian/_expand.py` | Condition Cartesian product |
| Intent service API | `src/datacloud_knowledge/intent/service.py` | `*_with_session()` functions |
| OWL import executor | `src/datacloud_knowledge/ingestion/owl_import/importer/executor.py` | Called by CLI `import-terms` |
| OWL import pipeline | `src/datacloud_knowledge/ingestion/owl_import/importer/runner.py` | precheck → executor → callback |
| OWL package generator | `src/datacloud_knowledge/ingestion/owl_generate/generator.py` | DB schema → OWL XML package |
| Internationalization | `src/datacloud_knowledge/i18n/prompts.py` | zh_CN/en_US prompts, labels |
| SQL assets (source) | `db/ddl/knowledge/`, `db/seed/knowledge/`, `db/migrations/` | Packaged into wheel at `adapters/opengauss/_db/sql_assets/` |
| DB operational scripts | `db/scripts/` | apply, verify, backfill, migrate (use `python db/scripts/*.py`) |
| ER diagram | `db/er/whale_datacloud.mmd` | Mermaid ER source |

## CODE MAP

| Symbol | Type | Location | Role |
|--------|------|----------|------|
| `create_reader()` | function | `adapters/__init__.py` | Factory for TermReader instances |
| `create_engine()` | function | `adapters/__init__.py` | Factory for TermSearchEngine instances |
| `create_writer()` | function | `adapters/__init__.py` | Factory for TermWriter instances |
| `create_bulk_importer()` | function | `adapters/__init__.py` | Factory for BulkImportAdapter |
| `ensure_schema()` | function | `adapters/__init__.py` | Schema lifecycle management |
| `backfill_tsvector()` | function | `adapters/__init__.py` | Jieba tsvector backfill |
| `backfill_embeddings()` | function | `adapters/__init__.py` | Embedding vector backfill |
| `PostgresTermReader` | class | `adapters/opengauss/reader.py` | TermReader implementation |
| `PostgresTermWriter` | class | `adapters/opengauss/writer.py` | TermWriter implementation |
| `PostgresSearchEngine` | class | `adapters/opengauss/engine.py` | TermSearchEngine implementation |
| `BulkImportAdapter` | class | `adapters/opengauss/import_writer.py` | Psycopg batch import writer |
| `DatabaseContext` | class | `adapters/opengauss/_db/context.py` | Transaction-local search_path |
| `ParsedDatabaseUrl` | dataclass | `adapters/opengauss/_db/url.py` | Normalized DB target |
| `TermReader` | protocol | `contracts/protocols.py` | Read-side interface (18 methods) |
| `TermSearchEngine` | protocol | `contracts/protocols.py` | Search-side interface (3 methods) |
| `TermWriter` | protocol | `contracts/protocols.py` | Write-side interface (8 methods) |
| `TagFilter` | Pydantic model | `contracts/types.py` | Tag filtering |
| `SearchTermsResult` | Pydantic model | `contracts/types.py` | Paginated search result |
| `FieldResolutionResult` | dataclass | `contracts/types.py` | Field alias resolution |
| `resolve_field_aliases()` | function | `provider.py` | Public: field alias resolution |
| `search_terms_by_type()` | function | `provider.py` | Public: typed term search |
| `prepare_query_clarification()` | function | `provider.py` | Public: clarification analysis |
| `finalize_query_clarification()` | function | `provider.py` | Public: clarification finalize |
| `get_object_props_by_code()` | function | `provider.py` | Public: object properties |
| `get_prop_enum_values()` | function | `provider.py` | Public: property enum values |
| `search_terms_with_fallback()` | function | `retrieval/orchestration.py` | Exact → BM25 orchestration |
| `analyze_query_clarification()` | function | `intent/clarification/api.py` | Clarification analysis core |
| `disambiguate()` | function | `intent/disambiguation.py` | Term disambiguation |
| `generate()` | function | `ingestion/owl_generate/generator.py` | OWL package generator |
| `run()` | function | `ingestion/owl_import/importer/executor.py` | OWL import executor |

## CONVENTIONS

### Layer import constraints (hard rule)

- **Non-adapter code MUST NOT import SQLAlchemy or psycopg** — all DB access goes through `adapters` factories (`create_reader`/`create_engine`/`create_writer`).
- **Non-adapter code MUST NOT import ORM models** — `adapters/opengauss/_db/models.py` is private. Models are not exposed across layers.
- **Non-adapter code MUST NOT import session factories** — `adapters/opengauss/_db/connection.py` is private. Session lifecycle is managed by adapter factory.
- **`_db/` is private** — external code must not import from `adapters/opengauss/_db/` directly. Only `adapters/__init__.py` exposes public functions from there.
- **Module path correctness** — `import_module` paths are not statically checked by ruff. Verify paths manually. Example: `datacloud_knowledge.embedding` is actually `datacloud_knowledge.retrieval.embedding`.

### General conventions

- **Version mismatch**: `pyproject.toml` version is `0.1.0`; runtime `__version__` is `0.2.0`. Check both before release/version work.
- **`intent/__init__.py` exports 56+ symbols** — this is the legacy/public API surface. Preserve existing names unless coordinating downstream changes with `datacloud-analysis`.
- **DB SQL should use bare table names** — schema is injected through `DatabaseContext` / connection `search_path`. Only information_schema or schema-management code may use schema-qualified names.
- **Backend selection**: Defaults to `"opengauss"`. Override via `DATACLOUD_KNOWLEDGE_BACKEND` env var or explicit parameter. Only `opengauss` is currently registered.
- **`contracts/` has zero external dependencies** — pure protocols and dataclasses. Safe to import from anywhere.
- **Ruff per-file ignores**: Root config has package-specific ignores for legacy complexity and dynamic SQL. Do not add new ignores without narrowing them to the smallest possible file.

## TESTS

Run from repo root (inherited from workspace):

```bash
uv run pytest packages/datacloud-knowledge/tests                    # All tests
uv run pytest packages/datacloud-knowledge/tests -m db_integration  # DB integration tests
uv run pytest packages/datacloud-knowledge/tests/intent             # Intent-only tests
```

| Area | Tests |
|------|-------|
| Intent/clarification | `tests/intent/test_clarification*.py` (6 files) |
| Intent/disambiguation | `tests/intent/test_disambiguation.py` |
| Intent/matching | `tests/intent/test_matching.py` |
| Intent/recall | `tests/intent/test_typed_recall.py`, `test_scope_recall_clause.py` |
| Intent/aliases | `tests/intent/test_resolve_field_aliases.py` |
| Intent service | `tests/intent/test_service_vector_toggle.py` |
| Importer | `tests/test_importer.py`, `tests/importer/test_owl_converter.py` |
| OWL generator | `tests/test_owl_gen_multiview.py` |
| Provider facade | `tests/provider/test_provider.py` |

**Test configuration:**
- `asyncio_mode = "auto"` (set in package `pyproject.toml`)
- `conftest.py` at `tests/intent/` registers `intent` and `db_integration` markers
- Root pytest config only references older `tests/db`/`tests/ontology` paths — prefer package-local commands above
- DB integration tests require `DATACLOUD_DB_*` env vars or `.env` file in `tests/`

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

**Note**: `db/scripts/` are operational tooling scripts that predate the CLI restructure. The CLI commands above are the preferred interface for schema management, but db scripts remain available for backward compatibility. See `db/AGENTS.md` for the full DB asset guide.

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

- **Do NOT import SQLAlchemy or psycopg outside `adapters/`** — use factory functions (`create_reader`/`create_engine`/`create_writer`).
- **Do NOT import ORM models directly** — `adapters/opengauss/_db/models.py` is private. Models are not exposed across layers.
- **Do NOT import from `adapters/opengauss/_db/` directly** — `_db/` is private. Only `adapters/__init__.py` exposes public functions.
- **Do NOT import from old module paths** — `db_url.py`, `knowledge_search/db/*`, `knowledge_build/`, `owl_gen/`, `query/`, `db/` (source) modules no longer exist. Use new paths.
- **Do NOT hard-code `whale_datacloud.` in SQL** — use `DatabaseContext` / connection `search_path`.
- **Do NOT use wildcard imports** — except in existing compatibility shim files with explicit ruff exceptions.
- **Do NOT use unqualified `# type: ignore`** — must include error code (enforced by root ruff/mypy).
- **Do NOT add production `print()` calls** — only `scripts/manual/*.py` has a ruff override for this.
- **Do NOT bypass importer precheck** — OWL import failure must roll back the whole import as a single transaction.
- **Do NOT split importer writes across independent transactions** — all entity writers share one transaction context.

## NOTES

- **Architecture restructure (2026-05)**: Old modules (`db/`, `query/`, `knowledge_build/`, `knowledge_search/`, `owl_gen/`) were reorganized into the six-module structure above. No compatibility shims exist for old import paths.
- **`db/` is still present** as source SQL assets (DDL, seed, migrations, scripts). These are packaged into the wheel at `adapters/opengauss/_db/sql_assets/`. See `db/AGENTS.md` for the full DB asset guide.
- **Only `opengauss` backend is registered** — the adapter factory supports backend selection by env var, but no MySQL or other backends are implemented yet.
- **`file_store/`** has no implementation files; do not import from it.
- **LSP/Pyright baseline**: Pre-existing diagnostics in `adapters/opengauss/bm25.py` and some legacy shims exist. Treat them as baseline unless your change touches those paths.
- **`TODO(ontology)`**: ontology_code filtering in clarification is not complete.
- **`intent/__init__.py`** exports a large legacy surface (~56 symbols). Do not rename public exports without coordinating with downstream `datacloud-analysis` consumers.
