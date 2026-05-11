# AGENTS.md

**Module:** db
**Purpose:** Source SQL assets, schema scripts, migrations, ER/docs

## OVERVIEW

This directory is the source-of-truth SQL asset tree. Wheel packaging copies `ddl/knowledge`, `seed/knowledge`, and `migrations` into `datacloud_knowledge.resources.sql.*`.

## STRUCTURE

```text
db/
├── ddl/knowledge/              # Complete schema DDL, 00..99 order
├── seed/knowledge/             # Built-in seed rows, idempotent
├── migrations/                 # Existing DB upgrades; mostly idempotent
├── data_fixes/                 # Manual data synchronization/fixes
├── scripts/                    # Operational Python scripts
├── er/                         # Mermaid ER source
└── docs/                       # Ext attrs design notes
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Full schema DDL | `ddl/knowledge/00_create_schema.sql` -> `99_indexes_constraints.sql` | `00_` is destructive |
| Built-in term types | `seed/knowledge/01_term_type_builtin.sql` | `ON CONFLICT DO NOTHING` |
| Existing DB upgrades | `migrations/` | Apply selectively to deployed DBs |
| Ext attr sync | `data_fixes/99_sync_ontology_ext_attrs.sql` | Manual data fix |
| ER diagram | `er/whale_datacloud.mmd` | Name still uses old schema label |
| Apply schema | `scripts/apply_whale_datacloud.py` | DDL then seed |
| Verify schema | `scripts/verify_whale_datacloud.py` | Table/structure checks |
| Backfill jieba tsvector | `scripts/backfill_jieba_tsvector.py` | Uses `DATACLOUD_KNOWLEDGE_BACKFILL_BATCH_SIZE` |
| Migrate embeddings | `scripts/migrate_term_name_embeddings.py` | Uses target `DATACLOUD_DB_*` and source `DATACLOUD_SOURCE_DB_*` |

## EXECUTION ORDER

| Phase | Directory | Rule |
|-------|-----------|------|
| DDL | `ddl/knowledge/` | New schema/bootstrap only; `00_create_schema.sql` can drop old objects |
| Migrations | `migrations/` | Existing schema upgrades; do not run blindly after full DDL |
| Seed | `seed/knowledge/` | Safe to repeat if statements remain idempotent |
| Data fixes | `data_fixes/` | Manual, case-specific |

## COMMANDS

```bash
python db/scripts/apply_whale_datacloud.py
python db/scripts/apply_whale_datacloud.py --seed-only
python db/scripts/verify_whale_datacloud.py
python db/scripts/backfill_jieba_tsvector.py --help
python db/scripts/migrate_term_name_embeddings.py --help
```

## CONVENTIONS

- Directory names are `knowledge`, not `whale_datacloud`; some script/ER filenames still retain historical names.
- Keep DDL filenames ordered with numeric prefixes. DDL order is the dependency graph.
- New full-schema columns belong in `ddl/knowledge/*`; deployed DB deltas also need a migration.
- Scripts should consume `DATACLOUD_DB_*` via `datacloud_knowledge.db.url` helpers where possible.
- SQL intended for app runtime should avoid schema-qualified table names; schema is injected through connection/search-path code.

## ANTI-PATTERNS

- Do not run destructive DDL against production unless explicitly requested.
- Do not update `db/ddl/knowledge` without checking wheel `force-include` paths in package `pyproject.toml`.
- Do not treat `migrations/` as bootstrap order for new databases; full DDL already includes current columns.
