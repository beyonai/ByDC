# PROJECT KNOWLEDGE BASE

**Generated:** 2026-05-11
**Commit:** d960caf2
**Branch:** main

## OVERVIEW

`datacloud-knowledge` is the knowledge SDK package for term retrieval, ontology import/export, intent disambiguation, and NL-to-knowledge-query support. It is a Python >=3.12 `src/` package in the uv workspace, with SQL assets packaged into the wheel.

## STRUCTURE

```text
packages/datacloud-knowledge/
├── src/datacloud_knowledge/
│   ├── db/                    # DB URL parsing, schema lifecycle, SQLAlchemy sessions
│   ├── intent/                # recall, disambiguation, clarification, scoring
│   ├── query/                 # NL semantic tree, search, fuzzy, embeddings
│   ├── knowledge_build/       # OWL import API and DB writer pipeline
│   ├── knowledge_search/      # typed term/alias/object-property lookup facade
│   ├── owl_gen/               # business DB schema -> OWL import package generator
│   └── resources/sql/         # packaged SQL resources from db/*
├── db/                        # source SQL assets, migrations, scripts, ER/docs
├── tests/                     # pytest tests by domain
└── scripts/manual/            # manual/eval scripts, print allowed by root ruff override
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Public lightweight SDK exports | `src/datacloud_knowledge/__init__.py` | Lazy exports keep optional deps out of CLI imports |
| CLI entry | `src/datacloud_knowledge/cli.py` | Console script: `datacloud-knowledge` |
| DB URL/schema resolution | `src/datacloud_knowledge/db/url.py` | Parses split env vars and PostgreSQL/OpenGauss/JDBC URLs |
| Schema lifecycle | `src/datacloud_knowledge/db/schema.py` | Uses packaged/fallback SQL resources |
| NL -> query tree | `src/datacloud_knowledge/query/sql_engine.py` | Largest core file; singleton service surface |
| Search recall | `src/datacloud_knowledge/query/search/` | BM25, vector, substring, jieba, RRF |
| Intent service API | `src/datacloud_knowledge/intent/service.py` | `*_with_session` functions for external consumers |
| Multi-turn clarification | `src/datacloud_knowledge/intent/clarification/api.py` | Uses postprocess/confirm/cartesian helpers |
| Knowledge provider facade | `src/datacloud_knowledge/provider.py` | Thin function-mode provider facade |
| OWL import HTTP router | `src/datacloud_knowledge/knowledge_build/router.py` | FastAPI `APIRouter(prefix="/build")` |
| OWL import pipeline | `src/datacloud_knowledge/knowledge_build/importer/runner.py` | precheck -> executor -> callback |
| Knowledge search facade | `src/datacloud_knowledge/knowledge_search/term_search.py` | Typed search, aliases, property values |
| OWL package generation | `src/datacloud_knowledge/owl_gen/generator.py` | Reads DB schema, calls renderers, writes package |
| SQL assets | `db/ddl/knowledge`, `db/seed/knowledge`, `db/migrations` | Force-included in wheel |

## CODE MAP

| Symbol | Type | Location | Role |
|--------|------|----------|------|
| `SQLKnowledgeGraphQuery` | class | `query/sql_engine.py` | Main NL knowledge-query service |
| `DatabaseContext` | class | `db/context.py` | Transaction-local `search_path` management |
| `ParsedDatabaseUrl` | dataclass | `db/url.py` | Normalized DB target from env/JDBC/libpq URL |
| `KnowledgeProvider` | protocol | `provider.py` | Public provider facade contract |
| `run()` | function | `knowledge_build/importer/runner.py` | Full OWL precheck/import/callback flow |
| `generate()` | function | `owl_gen/generator.py` | End-to-end OWL package generator |
| `search_terms_by_type()` | function | `knowledge_search/term_search.py` | Typed term search with filters/BM25 fallback |
| `typed_multi_recall_batch()` | function | `intent/batch_recall.py` | Batched typed recall core |
| `disambiguate()` | function | `intent/disambiguation.py` | Candidate disambiguation and path graph logic |
| `analyze_query_clarification()` | function | `intent/clarification/api.py` | Clarification analysis entry |

## CONVENTIONS

- Package metadata currently has `pyproject.toml` version `0.1.0`; runtime `__version__` is `0.2.0`. Check both before release/version work.
- Root package exports only 10 lightweight lazy names. Do not expand top-level imports if it pulls in SQLAlchemy/boto3/matplotlib during CLI startup.
- `intent/__init__.py` exports 56 legacy/public symbols. Preserve names unless coordinating downstream `datacloud-analysis` and byclaw-data changes.
- DB code must use schema resolution and `search_path`; SQL should use bare table names except information_schema/schema-management code.
- SQL resources live in source checkout under `db/ddl/knowledge`, `db/seed/knowledge`, `db/migrations`, and are packaged under `datacloud_knowledge.resources.sql.*`.
- `db_url.py` and `knowledge_search/db/*` are compatibility shims. New imports should target `datacloud_knowledge.db.*`.
- Ruff root config has package-specific ignores for legacy complexity and dynamic SQL. Do not add new ignores without narrowing them to the smallest file.

## TESTS

| Area | Tests |
|------|-------|
| Importer | `tests/importer/`, `tests/test_importer.py` |
| OWL generator | `tests/test_owl_gen_multiview.py` |
| Intent/clarification | `tests/intent/` |
| Provider facade | `tests/provider/test_provider.py` |
| Query search validation | `tests/query/search/test_vector_validation.py` |

`pyproject.toml` sets `asyncio_mode = "auto"` and marker `db_integration`. Root pytest config only names older `tests/db`/`tests/ontology` paths, so prefer package-local pytest commands when working here.

## COMMANDS

```bash
uv sync
uv run ruff format packages/datacloud-knowledge
uv run ruff check packages/datacloud-knowledge
uv run mypy packages/datacloud-knowledge/src/datacloud_knowledge
uv run pytest packages/datacloud-knowledge/tests
uv run --package datacloud-knowledge datacloud-knowledge --help
```

DB commands from package root:

```bash
python db/scripts/apply_whale_datacloud.py
python db/scripts/verify_whale_datacloud.py
python db/scripts/backfill_jieba_tsvector.py
python db/scripts/migrate_term_name_embeddings.py --help
```

## ENVIRONMENT

| Variable | Purpose |
|----------|---------|
| `DATACLOUD_DB_HOST`, `DATACLOUD_DB_PORT`, `DATACLOUD_DB_DATABASE` | Target knowledge DB |
| `DATACLOUD_DB_USER`, `DATACLOUD_DB_PASSWORD`, `DATACLOUD_DB_TYPE` | DB credentials/type |
| `DATACLOUD_DB_SCHEMA` | Target schema; default behavior resolves to `whale_datacloud` |
| `DATACLOUD_INTENT_DEBUG` | Enables intent package debug logger |
| `DATACLOUD_INTENT_ENABLE_VECTOR` | Toggles vector recall in intent service tests/runtime |
| `DATACLOUD_KNOWLEDGE_BACKFILL_BATCH_SIZE` | Jieba tsvector backfill batch size |
| `DATACLOUD_SOURCE_DB_*` | Source DB for embedding migration script |

## ANTI-PATTERNS

- Do not hard-code `whale_datacloud.` in application SQL. Use `DatabaseContext` / connection `search_path`.
- Do not import from compatibility shims in new code (`db_url.py`, `knowledge_search/db/*`).
- Do not use wildcard imports except in existing compatibility shim files already covered by ruff exceptions.
- Do not use unqualified `# type: ignore`; root mypy/ruff require error codes.
- Do not add production `print()` calls; only `scripts/manual/*.py` has a package ruff override.
- Do not bypass importer precheck or split importer writes across independent transactions; failure must roll back the whole import.

## NOTES

- `src/datacloud_knowledge/file_store/` currently has no implementation files; old local guidance was removed as stale.
- LSP/Pyright currently reports pre-existing diagnostics in `query/sql_engine.py`, `query/search/bm25.py`, and the compatibility wildcard shim. Treat them as baseline unless your change touches those paths.
- `TODO(ontology)` remains in clarification docs/AGENTS: ontology_code filtering is not complete.
