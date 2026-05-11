# AGENTS.md

**Module:** knowledge_build
**Purpose:** OWL import API and database write pipeline

## OVERVIEW

Knowledge package import flow: parse OWL files, convert into internal rows, precheck references, write all entities in one transaction, then optionally notify a callback.

## STRUCTURE

```text
knowledge_build/
├── router.py                  # FastAPI APIRouter(prefix="/build")
├── schema.py                  # Pydantic request/response models
└── importer/
    ├── runner.py              # precheck -> executor -> notifier
    ├── precheck.py            # Full in-memory validation
    ├── executor.py            # Transaction/schema orchestration
    ├── writer.py              # Batched SQL writes
    ├── _helpers.py            # Shared DB helper functions
    ├── owl_parser.py          # OWL XML parsing
    ├── owl_converter.py       # OWL -> internal structures
    ├── notifier.py            # Callback delivery
    └── snowflake.py           # ID generation
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| HTTP precheck endpoint | `router.py:precheck_import_package()` | `/build/import-package/precheck` |
| HTTP run endpoint | `router.py:run_import_package()` | `/build/import-package/run` |
| Full import entry | `importer/runner.py:run()` | Precheck failure still can notify callback |
| Transaction orchestration | `importer/executor.py` | Applies DB schema context |
| Batched writes | `importer/writer.py` | Entity-specific `_batch_process_*` functions |
| Shared DB helpers | `importer/_helpers.py` | Keep here to avoid cycles |
| OWL parsing/conversion | `importer/owl_parser.py`, `importer/owl_converter.py` | XML model normalization |
| Precheck rules | `importer/precheck.py` | Ontology files are validated but not inserted as rows |
| Tests | `tests/importer/`, `tests/test_importer.py` | Converter/parser/writer/importer coverage |

## FLOW

```text
folder_path
  -> precheck.run()
  -> executor.run() in one transaction
  -> writer batch functions
  -> notifier callback if configured
  -> RunResult
```

## CONVENTIONS

- Import writes must be all-or-nothing. Keep executor transaction boundaries intact.
- Use `DatabaseContext` / search path rather than schema-qualified SQL.
- `notifier.py` has a targeted `S310` ruff ignore for callback URLs; do not broaden it.
- `owl_parser.py` has XML naming/security ruff ignores; keep parser-specific quirks isolated there.
- Built-in term types are protected from deletion in writer logic.

## ANTI-PATTERNS

- Do not skip precheck before DB writes.
- Do not insert ontology files directly; precheck documents that ontology files are not imported as DB rows.
- Do not let callback delivery failure change the import result after DB work has succeeded/failed.
- Do not move helper functions back into executor/writer if that creates circular imports.
